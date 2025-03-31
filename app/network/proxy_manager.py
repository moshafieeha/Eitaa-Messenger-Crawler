import random
import re
import requests
import time
from app.config import config

class ProxyManager:
    """
    Handles proxy management and rotation for the crawler.
    Responsible for fetching, testing, and providing proxies.
    """
    
    def __init__(self):
        """Initialize the proxy manager with an empty pool"""
        self.proxy_pool = []
        self.last_refresh = 0
        self.refresh_interval = config.REFRESH_INTERVAL
    
    def fetch_proxy_list(self):
        """
        Fetch proxies from multiple sources and return a list of valid ones
        """
        urls = [
            "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all",
            "https://proxylist.geonode.com/api/proxy-list?limit=50&page=1&sort_by=lastChecked&sort_type=desc&protocols=http",
            "https://www.proxy-list.download/api/v1/get?type=http",
            "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
            "https://openproxylist.xyz/http.txt"
        ]
        proxies = set()
        proxy_pattern = re.compile(r'^\d+\.\d+\.\d+\.\d+:\d+$')

        for url in urls:
            try:
                response = config.SESSION.get(url, timeout=30)
                response.raise_for_status()
                if "proxyscrape" in url or "proxy-list.download" in url or "github" in url or "openproxylist" in url:
                    raw_proxies = response.text.strip().split('\n')
                    valid_proxies = [p for p in raw_proxies if proxy_pattern.match(p.strip())]
                    proxies.update(f"http://{p.strip()}" for p in valid_proxies)
                    config.logger.info(f"Fetched {len(valid_proxies)} proxies from {url}")
                elif "geonode" in url:
                    data = response.json()
                    valid_proxies = [f"{p['ip']}:{p['port']}" for p in data['data']]
                    proxies.update(f"http://{p}" for p in valid_proxies)
                    config.logger.info(f"Fetched {len(valid_proxies)} proxies from {url}")
            except Exception as e:
                config.logger.warning(f"Proxy fetch failed from {url}: {e}")
        return list(proxies)
    
    def test_proxy(self, proxy):
        """
        Test if a proxy is working properly
        
        Args:
            proxy: The proxy to test
            
        Returns:
            bool: True if proxy is working, False otherwise
        """
        from time import sleep
        for attempt in range(2):
            try:
                response = requests.get("https://www.google.com", 
                                      proxies={"http": proxy, "https": proxy}, 
                                      timeout=30)
                if response.status_code != 200:
                    config.logger.debug(f"Proxy {proxy} connectivity test failed, status {response.status_code}, attempt {attempt + 1}")
                    return False
                response = requests.get("http://httpbin.org/ip", 
                                      proxies={"http": proxy, "https": proxy}, 
                                      timeout=30)
                if response.status_code != 200:
                    config.logger.debug(f"Proxy {proxy} IP test failed, status {response.status_code}, attempt {attempt + 1}")
                    return False
                proxy_ip = response.json()["origin"]
                local_ip = self._get_local_ip()
                if local_ip is None or proxy_ip == local_ip:
                    config.logger.debug(f"Proxy {proxy} invalid, local IP {local_ip}, proxy IP {proxy_ip}, attempt {attempt + 1}")
                    return False
                config.logger.debug(f"Proxy {proxy} valid, IP {proxy_ip}, attempt {attempt + 1}")
                return True
            except Exception as e:
                config.logger.debug(f"Proxy {proxy} test failed: {e}, attempt {attempt + 1}")
                if attempt == 1:
                    return False
                sleep(2)
        return False
    
    def _get_local_ip(self):
        """Get the local IP address"""
        try:
            response = requests.get("http://httpbin.org/ip", timeout=15)
            return response.json()["origin"]
        except Exception as e:
            config.logger.warning(f"Failed to get local IP: {e}")
            return None
    
    def refresh_proxy_pool(self):
        """
        Refresh the proxy pool if it's empty or the refresh interval has passed
        """
        current_time = time.time()
        if current_time - self.last_refresh < self.refresh_interval and self.proxy_pool:
            return
        
        config.logger.info("Refreshing proxy pool")
        new_proxies = self.fetch_proxy_list()
        self.proxy_pool = [proxy for proxy in new_proxies if self.test_proxy(proxy)]
        self.last_refresh = current_time
        config.logger.info(f"Proxy pool updated with {len(self.proxy_pool)} proxies")
    
    def get_random_proxy(self):
        """
        Get a random proxy from the pool
        
        Returns:
            str: A proxy URL or None if no proxies are available
        """
        self.refresh_proxy_pool()
        if not self.proxy_pool:
            config.logger.warning("No proxies available")
            return None
        return random.choice(self.proxy_pool)
    
    def get_proxy_count(self):
        """
        Get the number of proxies in the pool
        
        Returns:
            int: The number of proxies
        """
        return len(self.proxy_pool)
    
    def check_proxy(self):
        """
        Check if proxies are available and working
        
        Returns:
            tuple: (bool, str) indicating success/failure and a message
        """
        self.refresh_proxy_pool()
        if not self.proxy_pool:
            config.logger.warning("No proxies found")
            return False, "No proxies"
        
        proxy = self.get_random_proxy()
        try:
            response = requests.get("http://httpbin.org/ip", 
                                   proxies={"http": proxy, "https": proxy}, 
                                   timeout=15)
            ip = response.json()["origin"]
            return True, f"OK (IP: {ip})"
        except requests.exceptions.RequestException as e:
            config.logger.warning(f"Proxy check failed for {proxy}: {e}")
            return False, f"Failed: {e}" 