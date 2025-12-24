import requests
import sys

class SyncApi:
    """
    A lightweight MediaWiki API client designed for syncing operations.
    Handles persistent sessions, login (including 2FA/BotPassword), CSRF tokens, and Captcha.
    """
    def __init__(self, api_url, username=None, password=None, user_agent='mediawiki-sync-manager/1.0'):
        self.api_url = api_url
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': user_agent})
        self.csrf_token = None
        self.logged_in = False

    def request(self, params, method='GET'):
        """Base request method with error handling."""
        p = {
            'format': 'json',
            'formatversion': 2,
            **params
        }
        
        try:
            if method == 'POST':
                resp = self.session.post(self.api_url, data=p, timeout=30)
            else:
                resp = self.session.get(self.api_url, params=p, timeout=30)
            
            resp.raise_for_status()
            data = resp.json()
            
            if 'error' in data:
                # Handle Captcha specifically if it bubbles up here (though usually it's in edit response)
                code = data['error'].get('code')
                info = data['error'].get('info', 'Unknown error')
                raise RuntimeError(f"API Error [{code}]: {info}")
                
            return data
        except Exception as e:
            print(f"[API ERROR] {e}", file=sys.stderr)
            raise

    def login(self):
        """Performs a 2-step login flow."""
        if not self.username or not self.password:
            print("No credentials provided. Skipping login (read-only mode?).")
            return

        print(f"Logging in as {self.username}...")
        
        # Step 1: Get Login Token
        login_token = self.get_token('login')
        
        # Step 2: Send Credentials
        params = {
            'action': 'login',
            'lgname': self.username,
            'lgpassword': self.password,
            'lgtoken': login_token
        }
        
        data = self.request(params, method='POST')
        
        # Check result
        result = data.get('login', {}).get('result')
        if result == 'Success':
            print("Login successful.")
            self.logged_in = True
        elif result == 'Failed':
             raise RuntimeError("Login failed. Check credentials.")
        else:
            raise RuntimeError(f"Login failed: {data.get('login', {})}")

    def get_token(self, type='csrf'):
        """Fetches a token of the specified type."""
        params = {'action': 'query', 'meta': 'tokens', 'type': type}
        data = self.request(params)
        return data['query']['tokens'].get(f'{type}token')

    def ensure_csrf_token(self):
        """Ensures we have a valid CSRF token."""
        if not self.csrf_token:
            self.csrf_token = self.get_token('csrf')
        return self.csrf_token

    def edit_page(self, title, text, summary, create_only=False):
        """
        Attempts to edit (or create) a page.
        Handles Captcha by prompting the user via stdin.
        """
        if not self.logged_in:
            self.login()

        token = self.ensure_csrf_token()
        
        params = {
            'action': 'edit',
            'title': title,
            'text': text,
            'summary': summary,
            'token': token,
            'watchlist': 'nochange'
        }
        if create_only:
            params['createonly'] = True

        return self._send_edit_request(params)

    def _send_edit_request(self, params):
        """Internal helper to send edit request and handle Captcha loop."""
        while True:
            data = self.request(params, method='POST')
            
            if 'edit' in data:
                result = data['edit'].get('result')
                if result == 'Success':
                    print(f"Successfully edited '{params['title']}'.")
                    return True
                
                # Check for Captcha in the editing response
                if 'captcha' in data['edit']:
                    captcha = data['edit']['captcha']
                    if not self._solve_captcha(captcha, params):
                        # User aborted captcha
                        return False
                    continue # Retry with captcha info added to params
            
            # If we get here, something else happened (error usually raised in request(), but strictly speaking:)
            if 'error' in data:
                # This block might be redundant if request() handles errors, 
                # but sometimes 'edit' failure isn't top-level error.
                print(f"Edit failed: {data}")
                return False
            
            return False

    def _solve_captcha(self, captcha_data, params):
        """
        Prompts user to solve captcha. Modifies params in-place to include answer.
        Returns True if solved, False if aborted.
        """
        captcha_url = captcha_data.get('url')
        captcha_id = captcha_data.get('id')
        question = captcha_data.get('question')
        
        print(f"\n[CAPTCHA REQUIRED] Type: {captcha_data.get('type')}")
        if captcha_url:
             print(f"Image URL: {self.api_url.replace('/api.php', '')}{captcha_url}")
             # Note needed if relative URL
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
