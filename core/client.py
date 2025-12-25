"""
MediaWikiClient - Unified API client for MediaWiki

Merges features from:
- exporter/api.py: rate limiting, maxlag, threading, retries
- tools/api.py: login, CSRF tokens, edit operations, captcha
"""
import time
import threading
import requests
from typing import Dict, Any, Optional
from .logger import get_logger


class MediaWikiClient:
    """
    A robust MediaWiki API client with:
    - Unified GET/POST requests
    - Rate limiting (maxlag, 429 handling)
    - Thread-safe with stop_event
    - Lazy CSRF token caching
    - Login and authentication
    - Edit operations with captcha support
    """
    
    def __init__(
        self,
        api_url: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        user_agent: str = 'LocalMediaWikiTools/1.0',
        maxlag: int = 5,
        sleep: float = 0.5
    ):
        self.api_url = api_url
        self.username = username
        self.password = password
        self.maxlag = maxlag
        self.sleep = sleep
        
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': user_agent})
        
        # Lazy-loaded tokens and state
        self._csrf_token: Optional[str] = None
        self._logged_in: bool = False
        
        # Logger
        self.logger = get_logger('client')
    
    # =========================================================================
    # REQUEST HANDLING (from exporter/api.py + tools/api.py)
    # =========================================================================
    
    def request(
        self,
        params: Dict[str, Any],
        method_or_event: str | threading.Event = 'GET',
        stop_event: Optional[threading.Event] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Unified request method handling GET and POST.
        
        Handles:
        - maxlag (server overload)
        - 429 (rate limiting)
        - Network errors with retry
        - JSON parse errors with retry
        
        Args:
            params: API parameters
            method_or_event: 'GET', 'POST', or threading.Event (backwards compat)
            stop_event: Optional threading.Event to cancel request
            
        Returns:
            JSON response dict, or None if stopped/cancelled
        """
        # Backwards compatibility: old signature was request(params, stop_event)
        if isinstance(method_or_event, threading.Event):
            stop_event = method_or_event
            method = 'GET'
        else:
            method = method_or_event
        
        request_params = {
            'format': 'json',
            'formatversion': 2,
            'maxlag': self.maxlag,
            **params
        }
        
        # Create dummy event if not provided
        if stop_event is None:
            stop_event = threading.Event()
        
        retry_count = 0
        max_retries = 10
        
        while not stop_event.is_set() and retry_count < max_retries:
            try:
                if method.upper() == 'POST':
                    resp = self.session.post(self.api_url, data=request_params, timeout=30)
                else:
                    resp = self.session.get(self.api_url, params=request_params, timeout=30)
                
                # Handle 429 Too Many Requests
                if resp.status_code == 429:
                    self.logger.warn("Rate limited (429). Waiting 10s...")
                    time.sleep(10)
                    retry_count += 1
                    continue
                
                resp.raise_for_status()
                data = resp.json()
                
                # Handle API errors
                error = data.get('error')
                if error:
                    code = error.get('code')
                    info = error.get('info', 'Unknown error')
                    
                    # Handle maxlag
                    if code == 'maxlag':
                        self.logger.debug(f"Server lagged. Waiting 5s...")
                        time.sleep(5)
                        retry_count += 1
                        continue
                    
                    # Other errors
                    raise RuntimeError(f"API Error [{code}]: {info}")
                
                # Success - sleep and return
                time.sleep(self.sleep)
                return data
                
            except requests.RequestException as e:
                self.logger.warn(f"Network error: {type(e).__name__}. Retrying in 5s...")
                time.sleep(5)
                retry_count += 1
                continue
                
            except ValueError as e:
                self.logger.warn(f"JSON parse error. Retrying in 5s...")
                time.sleep(5)
                retry_count += 1
                continue
        
        if retry_count >= max_retries:
            self.logger.error(f"Max retries ({max_retries}) exceeded.")
        
        return None
    
    # =========================================================================
    # AUTHENTICATION (from tools/api.py)
    # =========================================================================
    
    def login(self) -> bool:
        """
        Performs 2-step login flow.
        Returns True on success, False on failure.
        """
        if not self.username or not self.password:
            self.logger.debug("No credentials provided. Skipping login.")
            return False
        
        self.logger.info(f"Logging in as {self.username}...")
        
        # Step 1: Get login token
        login_token = self.get_token('login')
        
        # Step 2: Send credentials
        params = {
            'action': 'login',
            'lgname': self.username,
            'lgpassword': self.password,
            'lgtoken': login_token
        }
        
        data = self.request(params, method='POST')
        
        if data is None:
            self.logger.error("Login request failed.")
            return False
        
        result = data.get('login', {}).get('result')
        if result == 'Success':
            self.logger.info("Login successful.")
            self._logged_in = True
            return True
        elif result == 'Failed':
            self.logger.error("Login failed. Check credentials.")
            return False
        else:
            self.logger.error(f"Login failed: {data.get('login', {})}")
            return False
    
    @property
    def logged_in(self) -> bool:
        return self._logged_in
    
    # =========================================================================
    # TOKENS (from tools/api.py - now lazy)
    # =========================================================================
    
    def get_token(self, token_type: str = 'csrf') -> Optional[str]:
        """Fetch a token of the specified type."""
        params = {'action': 'query', 'meta': 'tokens', 'type': token_type}
        data = self.request(params)
        if data:
            return data.get('query', {}).get('tokens', {}).get(f'{token_type}token')
        return None
    
    @property
    def csrf_token(self) -> Optional[str]:
        """Lazy-loaded and cached CSRF token."""
        if self._csrf_token is None:
            self._csrf_token = self.get_token('csrf')
        return self._csrf_token
    
    def invalidate_csrf_token(self):
        """Force re-fetch of CSRF token on next use."""
        self._csrf_token = None
    
    # =========================================================================
    # EDIT OPERATIONS (from tools/api.py)
    # =========================================================================
    
    def edit_page(
        self,
        title: str,
        text: str,
        summary: str,
        create_only: bool = False
    ) -> bool:
        """
        Edit or create a page.
        Handles captcha by prompting user via stdin.
        
        Returns True on success, False on failure.
        """
        # Ensure logged in
        if not self._logged_in and self.username:
            self.login()
        
        params = {
            'action': 'edit',
            'title': title,
            'text': text,
            'summary': summary,
            'token': self.csrf_token,
            'watchlist': 'nochange'
        }
        if create_only:
            params['createonly'] = True
        
        return self._send_edit_request(params)
    
    def _send_edit_request(self, params: Dict[str, Any]) -> bool:
        """Send edit request with captcha loop."""
        while True:
            data = self.request(params, method='POST')
            
            if data is None:
                return False
            
            if 'edit' in data:
                result = data['edit'].get('result')
                if result == 'Success':
                    self.logger.info(f"Successfully edited '{params['title']}'.")
                    return True
                
                # Check for captcha
                if 'captcha' in data['edit']:
                    captcha = data['edit']['captcha']
                    if not self._solve_captcha(captcha, params):
                        return False
                    continue
            
            if 'error' in data:
                self.logger.error(f"Edit failed: {data}")
                return False
            
            return False
    
    def _solve_captcha(self, captcha_data: Dict, params: Dict) -> bool:
        """
        Prompts user to solve captcha.
        Modifies params in-place to include answer.
        Returns True if solved, False if aborted.
        """
        captcha_url = captcha_data.get('url')
        captcha_id = captcha_data.get('id')
        question = captcha_data.get('question')
        
        print(f"\n[CAPTCHA REQUIRED] Type: {captcha_data.get('type')}")
        if captcha_url:
            base_url = self.api_url.replace('/api.php', '')
            print(f"Image URL: {base_url}{captcha_url}")
        if question:
            print(f"Question: {question}")
        print(f"Captcha ID: {captcha_id}")
        
        answer = input("Enter Captcha Answer (or empty to abort): ").strip()
        if not answer:
            print("Aborted.")
            return False
        
        params['captchaid'] = captcha_id
        params['captchaword'] = answer
        return True
    
    # =========================================================================
    # UTILITY METHODS
    # =========================================================================
    
    def query(self, **kwargs) -> Optional[Dict]:
        """Shortcut for action=query."""
        return self.request({'action': 'query', **kwargs})
    
    def get_page_content(self, title: str) -> Optional[str]:
        """Get the wikitext content of a page."""
        data = self.query(
            titles=title,
            prop='revisions',
            rvprop='content',
            rvslots='main'
        )
        if data:
            pages = data.get('query', {}).get('pages', [])
            if pages and 'revisions' in pages[0]:
                return pages[0]['revisions'][0]['slots']['main']['content']
        return None
