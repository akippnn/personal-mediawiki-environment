import time
import threading
from typing import Dict, Any, Optional
import requests

class MediaWikiApi:
    """A robust wrapper for the MediaWiki API that handles errors, retries, and rate limiting."""

    def __init__(self, api_url: str, user_agent: str, maxlag: int, sleep: float):
        self.api_url = api_url
        self.sleep = sleep
        self.maxlag = maxlag
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': user_agent})
        # This is a good place to have a reference back to the logger
        self.logger = None

    def request(self, params: Dict[str, Any], stop_event: threading.Event) -> Optional[Dict[str, Any]]:
        """
        Makes a request to the API, handling errors, retries, and maxlag.
        Returns the JSON response dict, or None if the operation was stopped.
        """
        request_params = {
            'format': 'json',
            'formatversion': 2,
            'maxlag': self.maxlag,
            **params
        }

        while not stop_event.is_set():
            try:
                res = self.session.get(self.api_url, params=request_params, timeout=30)
                res.raise_for_status()

                if res.status_code == 429: # Too Many Requests
                    time.sleep(10)
                    continue

                data = res.json()
                error = data.get('error')
                if error:
                    code = error.get('code')
                    if code == 'maxlag':
                        time.sleep(5)
                        continue
                    raise RuntimeError(f"MediaWiki API error: {error.get('info', 'Unknown error')}")

                time.sleep(self.sleep)
                return data

            # --- IMPROVED EXCEPTION HANDLING ---
            except requests.RequestException as e:
                # Log the specific network error instead of failing silently.
                # This would have immediately shown a "ConnectionTimeout" or "DNS lookup failed" error.
                if self.logger:
                    self.logger(f"[NETWORK ERROR] {type(e).__name__}: {e}. Retrying in 5s...")
                time.sleep(5)
                continue
            except ValueError:
                if self.logger:
                    self.logger("[JSON ERROR] Failed to parse JSON response. Retrying in 5s...")
                time.sleep(5)
                continue

        return None

# To make this work, we'll slightly adjust the exporter to pass its debug method to the API class.
# In mediawiki_exporter/exporter.py __init__ method:
#
# class MediaWikiExporter:
#     def __init__(self, api_url: str, output_dir: str, debug: bool = False, **kwargs):
#         ...
#         self.api = MediaWikiApi(api_url=api_url, **kwargs)
#         self.api.logger = self.debug # Pass the debug logger to the API class
#         ...