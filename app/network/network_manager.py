from bs4 import BeautifulSoup
import requests
import json
from app.config import config
import time

class NetworkManager:
    """
    Handles all network-related operations for the crawler
    including making requests and performing connectivity checks.
    """
    
    def __init__(self, proxy_manager=None):
        self.session = config.SESSION
        self.headers = config.HEADERS
        self.proxy_manager = proxy_manager
    
    def fetch_channel_data(self, channel_id, retries=2, use_proxies=True):
        """
        Fetches channel data from Eitaa messenger
        
        Args:
            channel_id: The ID of the channel
            retries: Number of retry attempts
            use_proxies: Whether to use proxies for the request
            
        Returns:
            A tuple containing the data and any error message
        """
        url = f"https://eitaa.com/{channel_id}"
        proxy = self.proxy_manager.get_random_proxy() if use_proxies and self.proxy_manager else None
        proxies = {"http": proxy, "https": proxy} if proxy else None
        
        for attempt in range(retries):
            try:
                # Make the HTTP request with appropriate error handling
                response = self.session.get(url, headers=self.headers, timeout=15, proxies=proxies)
                
                # Handle HTTP errors with specific messages
                try:
                    response.raise_for_status()
                except requests.exceptions.HTTPError as http_err:
                    status_code = response.status_code
                    if status_code == 404:
                        return {"messages": [], "soup": None}, f"Channel not found (404): {channel_id}"
                    elif status_code == 403:
                        return {"messages": [], "soup": None}, f"Access forbidden (403) for channel: {channel_id}"
                    elif status_code == 429:
                        # Rate limiting - wait longer before retry
                        wait_time = min(60, (attempt + 1) * 20)
                        config.logger.warning(f"Rate limited (429) for {channel_id}. Waiting {wait_time}s before retry.")
                        time.sleep(wait_time)
                        continue
                    elif status_code >= 500:
                        return {"messages": [], "soup": None}, f"Server error ({status_code}) for channel: {channel_id}"
                    else:
                        raise http_err  # Re-raise for the outer exception handler
                
                # Parse HTML content
                try:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # Verify we have a valid page structure
                    if not self._verify_page_structure(soup, channel_id):
                        return {"messages": [], "soup": None}, "Invalid or changed page structure"
                    
                    # Extract messages with better error handling
                    messages = soup.select('.etme_widget_message_wrap.js-widget_message_wrap')
                    
                    # Check if we got an unexpected empty result
                    if not messages and self._appears_to_be_valid_channel_page(soup):
                        config.logger.warning(f"No messages found for {channel_id}, selector may have changed")
                        # Try alternative selectors if primary fails
                        messages = self._try_alternative_selectors(soup)
                    
                    # Return raw messages and soup for processing by crawler
                    raw_messages = []
                    for msg in messages:
                        raw_messages.append({"raw_message": msg, "channel_id": channel_id})
                    
                    ip = self._get_current_ip(proxies)
                    config.logger.info(f"Fetched {len(raw_messages)} messages from {channel_id} via {proxy or 'direct'} (IP: {ip})")
                    return {"messages": raw_messages, "soup": soup}, None
                    
                except Exception as parse_err:
                    config.logger.error(f"HTML parsing error for {channel_id}: {parse_err}")
                    return {"messages": [], "soup": None}, f"Parse error: {parse_err}"
                
            except requests.exceptions.ConnectionError as e:
                config.logger.warning(f"Connection error for {channel_id}: {e}")
                if attempt < retries - 1:
                    # Exponential backoff for connection errors
                    wait_time = (2 ** attempt) * 5
                    config.logger.info(f"Retrying {channel_id} in {wait_time}s, attempt {attempt + 2}/{retries}")
                    time.sleep(wait_time)
                    proxy = self.proxy_manager.get_random_proxy() if use_proxies and self.proxy_manager else None
                    proxies = {"http": proxy, "https": proxy} if proxy else None
                else:
                    config.logger.error(f"Connection failed for {channel_id} after {retries} attempts: {e}")
                    return {"messages": [], "soup": None}, f"Connection error: {e}"
                    
            except requests.exceptions.Timeout as e:
                config.logger.warning(f"Timeout for {channel_id}: {e}")
                if attempt < retries - 1:
                    config.logger.info(f"Retrying {channel_id}, attempt {attempt + 2}/{retries}")
                    proxy = self.proxy_manager.get_random_proxy() if use_proxies and self.proxy_manager else None
                    proxies = {"http": proxy, "https": proxy} if proxy else None
                else:
                    config.logger.error(f"Timeout for {channel_id} after {retries} attempts: {e}")
                    return {"messages": [], "soup": None}, f"Timeout: {e}"
                    
            except Exception as e:
                config.logger.warning(f"Fetch failed for {channel_id} via {proxy or 'direct'}: {e}")
                if attempt < retries - 1:
                    config.logger.info(f"Retrying {channel_id}, attempt {attempt + 2}/{retries}")
                    proxy = self.proxy_manager.get_random_proxy() if use_proxies and self.proxy_manager else None
                    proxies = {"http": proxy, "https": proxy} if proxy else None
                else:
                    config.logger.error(f"Fetch exhausted retries for {channel_id}: {e}")
                    return {"messages": [], "soup": None}, f"Error: {str(e)}"
                    
        return {"messages": [], "soup": None}, "Max retries reached"
    
    def _verify_page_structure(self, soup, channel_id):
        """
        Verify that the page structure matches what we expect from Eitaa
        
        Args:
            soup: BeautifulSoup object containing channel page
            channel_id: The ID of the channel
            
        Returns:
            bool: True if structure appears valid, False otherwise
        """
        try:
            # Check for key elements that should exist on a valid channel page
            # We'll use a more permissive approach to handle site changes
            required_elements = [
                # Check for these elements with broader selectors
                soup.select_one('div[class*="etme"]'),
                soup.select_one('[class*="channel"]'),
                soup.select_one('[class*="message"]'),
                # Check for title
                soup.title,
                # Check for any divs (most pages have divs)
                soup.select('div')
            ]
            
            # If at least two of the required elements are present, consider it valid
            if sum(1 for elem in required_elements if elem) >= 2:
                return True
            
            # Check for common error indicators
            error_indicators = [
                soup.select_one('[class*="error"]'),
                soup.select_one('div:contains("error")'),
                soup.select_one('div:contains("not found")')
            ]
            
            if any(error_indicators):
                error_text = next((e.get_text(strip=True) for e in error_indicators if e), "Unknown error")
                config.logger.warning(f"Error page detected for {channel_id}: {error_text}")
                return False
                
            # If we didn't find required elements or error indicators, page structure might have changed
            html_sample = str(soup)[:200] + "..." if soup else "None"
            config.logger.warning(f"Unexpected page structure for {channel_id}. Sample: {html_sample}")
            
            # More lenient check - if we have some content, assume it's valid
            if len(str(soup)) > 500:
                config.logger.info(f"Page has content for {channel_id}, proceeding with extraction attempt")
                return True
                
            return False
            
        except Exception as e:
            config.logger.error(f"Error verifying page structure for {channel_id}: {e}")
            return False
    
    def _appears_to_be_valid_channel_page(self, soup):
        """
        Check if the page appears to be a valid channel page
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            bool: True if it appears to be a valid channel page
        """
        # Check for channel header which should always be present
        return bool(soup.select_one('.etme_channel_info_header'))
    
    def _try_alternative_selectors(self, soup):
        """
        Try alternative selectors if the primary selector fails
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            list: Messages found with alternative selectors
        """
        # List of alternative selectors to try if the primary one fails
        alternative_selectors = [
            '.etme_widget_message',
            '.js-widget_message_wrap',
            '.message-container',
            '[class*="message"][class*="wrap"]'  # Fuzzy match for classes containing both "message" and "wrap"
        ]
        
        for selector in alternative_selectors:
            messages = soup.select(selector)
            if messages:
                config.logger.info(f"Found {len(messages)} messages using alternative selector: {selector}")
                return messages
                
        return []
    
    def _get_current_ip(self, proxies=None):
        """Get the current IP address being used"""
        try:
            response = requests.get("http://httpbin.org/ip", proxies=proxies, timeout=15)
            return response.json()["origin"]
        except Exception:
            return self.get_local_ip() or "unknown"
    
    def get_local_ip(self):
        """Get the local IP address"""
        try:
            response = requests.get("http://httpbin.org/ip", timeout=15)
            return response.json()["origin"]
        except Exception as e:
            config.logger.warning(f"Failed to get local IP: {e}")
            return None
            
    def check_internet(self):
        """Check if internet connectivity is available"""
        try:
            self.session.get("https://www.google.com", timeout=15)
            return True, "OK"
        except requests.exceptions.RequestException as e:
            config.logger.warning(f"Internet check failed: {e}")
            return False, f"Failed: {e}"
    
    def check_users_file(self):
        """Check if the users file exists and is valid"""
        try:
            with open(config.CHANNELS_FILE, 'r', encoding='utf-8') as f:
                channels = json.load(f)
                if not isinstance(channels, list):
                    config.logger.error(f"{config.CHANNELS_FILE} invalid: not a list")
                    return False, "Invalid: Not a list"
                if not channels:
                    config.logger.warning(f"{config.CHANNELS_FILE} empty")
                    return False, "Empty file"
                return True, "OK"
        except FileNotFoundError:
            config.logger.error(f"{config.CHANNELS_FILE} not found")
            return False, "Not found"
        except json.JSONDecodeError as e:
            config.logger.error(f"{config.CHANNELS_FILE} invalid JSON: {e}")
            return False, f"Invalid JSON: {e}"
        except Exception as e:
            config.logger.error(f"Users file check failed: {e}")
            return False, f"Error: {e}"
    
    def perform_initial_checks(self, require_proxies=True):
        """Perform all initial checks before starting the crawler"""
        checks = {
            "Internet": self.check_internet(),
            "Users File": self.check_users_file()
        }
        if require_proxies and self.proxy_manager:
            checks["Proxy"] = self.proxy_manager.check_proxy()
        
        status = {k: v[1] for k, v in checks.items()}
        config.logger.info(f"Initial checks: {status}")
        return all(check[0] for k, check in checks.items() if k != "Proxy" or require_proxies) 