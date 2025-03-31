from bs4 import BeautifulSoup
from datetime import datetime
import pytz
from app.config import config

class DataExtractor:
    """
    Extracts structured data from HTML content.
    Focuses on message and bio extraction from Eitaa messenger HTML.
    """
    def __init__(self):
        self.tz = pytz.timezone('Asia/Tehran')
    
    def extract_message_details(self, message, channel_id):
        """
        Extract message details from a BeautifulSoup element
        
        Args:
            message: BeautifulSoup element containing a message
            channel_id: The ID of the channel
            
        Returns:
            dict: Structured message data or None if extraction failed
        """
        try:
            # Handle both raw BS4 elements and dictionary inputs
            if isinstance(message, dict) and 'raw_message' in message:
                message = message['raw_message']
                channel_id = message.get('channel_id', channel_id)
                
            # Verify that we received a valid BS4 element
            if not hasattr(message, 'select_one'):
                config.logger.error(f"Invalid message format for {channel_id}: not a BeautifulSoup element")
                return None
                
            # Extract message ID using multiple strategies
            message_id = None
            id_extraction_methods = [
                lambda m: m.get('id'),
                lambda m: (m.select_one('.etme_widget_message') or {}).get('id'),
                lambda m: self._extract_id_from_data_post(m, channel_id),
                lambda m: self._extract_id_from_href(m, channel_id),
                lambda m: self._extract_id_from_attributes(m)
            ]
            
            for extract_method in id_extraction_methods:
                try:
                    message_id = extract_method(message)
                    if message_id:
                        break
                except Exception as e:
                    config.logger.debug(f"ID extraction method failed for {channel_id}: {e}")
            
            if not message_id:
                config.logger.warning(f"No ID found for message in {channel_id} after trying all extraction methods")
                return None
                
            try:
                message_id = int(message_id)
            except (ValueError, TypeError) as e:
                config.logger.warning(f"Invalid ID '{message_id}' in {channel_id}: {e}")
                return None

            # More robust context extraction
            context = message.select_one('.etme_widget_message') or message
            message_url = f"https://eitaa.com/{channel_id}/{message_id}"
            
            # Text extraction with fallbacks
            text = "No text"
            text_extraction_methods = [
                lambda c: c.select_one('.etme_widget_message_text.js-message_text'),
                lambda c: c.select_one('.etme_widget_message_text'),
                lambda c: c.select_one('.js-message_text'),
                lambda c: c.select_one('[class*="message"][class*="text"]'),
                lambda c: c.select_one('div.text'),
                lambda c: c  # Last resort, use the entire context
            ]
            
            for extract_method in text_extraction_methods:
                try:
                    text_elem = extract_method(context)
                    if text_elem:
                        text = text_elem.get_text(strip=True) if hasattr(text_elem, 'get_text') else str(text_elem)
                        if text and text != "No text":
                            break
                except Exception as e:
                    config.logger.debug(f"Text extraction method failed for {channel_id}: {e}")
            
            # View count extraction with error handling
            view_count = 0
            try:
                view_selectors = [
                    '.etme_widget_message_views',
                    '.message_views',
                    '[class*="view"][class*="count"]'
                ]
                
                for selector in view_selectors:
                    view_elem = context.select_one(selector)
                    if view_elem:
                        # Try different attributes that might contain the count
                        for attr in ['data-count', 'content', 'value']:
                            count_str = view_elem.get(attr)
                            if count_str:
                                try:
                                    view_count = int(count_str)
                                    break
                                except (ValueError, TypeError):
                                    pass
                        
                        # If attributes failed, try text content
                        if view_count == 0 and hasattr(view_elem, 'get_text'):
                            try:
                                view_text = view_elem.get_text(strip=True)
                                # Extract numbers from the text
                                import re
                                numbers = re.findall(r'\d+', view_text)
                                if numbers:
                                    view_count = int(numbers[0])
                            except (ValueError, IndexError, TypeError):
                                pass
                                
                        # If we found a count, stop searching
                        if view_count > 0:
                            break
            except Exception as e:
                config.logger.warning(f"Error extracting view count for {channel_id}: {e}")
            
            # Time extraction with multiple fallbacks
            posted_time = None
            time_extraction_methods = [
                lambda c: (c.select_one('.etme_widget_message_date time'), 'datetime', "%Y-%m-%dT%H:%M:%S%z"),
                lambda c: (c.select_one('.message_date time'), 'datetime', "%Y-%m-%dT%H:%M:%S%z"),
                lambda c: (c.select_one('time'), 'datetime', "%Y-%m-%dT%H:%M:%S%z"),
                lambda c: (c.select_one('[datetime]'), 'datetime', "%Y-%m-%dT%H:%M:%S%z"),
                lambda c: (c.select_one('.etme_widget_message_date'), 'data-time', "%Y-%m-%d %H:%M:%S"),
                lambda c: (c.select_one('[data-time]'), 'data-time', "%Y-%m-%d %H:%M:%S")
            ]
            
            for extract_method in time_extraction_methods:
                try:
                    time_elem, attr, fmt = extract_method(context)
                    if time_elem and time_elem.get(attr):
                        try:
                            if '%z' in fmt and not time_elem.get(attr).endswith(('Z', '+0000')):
                                # Add timezone if missing
                                time_str = time_elem.get(attr) + '+0000'
                            else:
                                time_str = time_elem.get(attr)
                                
                            posted_time = datetime.strptime(time_str, fmt)
                            break
                        except ValueError:
                            # Try alternative formats if the first one fails
                            for alt_fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"]:
                                try:
                                    posted_time = datetime.strptime(time_elem.get(attr), alt_fmt)
                                    posted_time = posted_time.replace(tzinfo=self.tz)
                                    break
                                except ValueError:
                                    continue
                            if posted_time:
                                break
                except Exception as e:
                    config.logger.debug(f"Time extraction method failed for {channel_id}: {e}")
                    
            # If we couldn't extract a timestamp, use the current time
            if not posted_time:
                config.logger.warning(f"No timestamp extracted for message {message_id} in {channel_id}, using current time")
                posted_time = datetime.now(self.tz)

            # Build and return the structured message data
            return {
                "_": "message",
                "id": message_id,
                "channel_id": channel_id,
                "url": message_url,
                "text": text,
                "view_count": view_count,
                "posted_time": posted_time.isoformat(),
                "crawled_at": datetime.now(self.tz).isoformat(),
                "extraction_errors": self._get_extraction_errors()
            }
            
        except Exception as e:
            config.logger.error(f"Unexpected error extracting message details for {channel_id}: {e}")
            return None
            
    def _extract_id_from_data_post(self, message, channel_id):
        """Extract message ID from data-post attribute"""
        try:
            data_post = (message.select_one('.etme_widget_message') or {}).get('data-post')
            if data_post:
                return int(data_post.split('/')[-1])
        except (ValueError, IndexError, AttributeError) as e:
            config.logger.debug(f"Failed to extract ID from data-post for {channel_id}: {e}")
        return None
        
    def _extract_id_from_href(self, message, channel_id):
        """Extract message ID from href attribute of links"""
        try:
            links = message.select('a[href*="' + channel_id + '"]')
            for link in links:
                href = link.get('href', '')
                parts = href.split('/')
                if len(parts) > 1 and parts[-2] == channel_id:
                    try:
                        return int(parts[-1])
                    except ValueError:
                        pass
        except Exception as e:
            config.logger.debug(f"Failed to extract ID from href for {channel_id}: {e}")
        return None
        
    def _extract_id_from_attributes(self, message):
        """Extract message ID from various attributes that might contain it"""
        try:
            # List of attributes that might contain the ID
            id_attrs = ['id', 'data-id', 'data-message-id', 'data-msg-id']
            
            # Try on the message element itself
            for attr in id_attrs:
                if hasattr(message, 'get') and message.get(attr):
                    try:
                        # Extract numeric part if attribute contains non-numeric characters
                        import re
                        match = re.search(r'\d+', message.get(attr))
                        if match:
                            return int(match.group(0))
                    except ValueError:
                        pass
                        
            # Try on child elements that might have the ID
            for attr in id_attrs:
                elements = message.select(f'[{attr}]')
                for elem in elements:
                    try:
                        if elem.get(attr):
                            match = re.search(r'\d+', elem.get(attr))
                            if match:
                                return int(match.group(0))
                    except (ValueError, AttributeError):
                        pass
        except Exception as e:
            config.logger.debug(f"Failed to extract ID from attributes: {e}")
        return None
        
    def _get_extraction_errors(self):
        """Return a list of extraction errors/warnings that occurred during processing"""
        return []  # Placeholder for future implementation to track warnings during extraction

    def extract_channel_bio(self, soup, channel_id):
        """
        Extract channel bio information from HTML
        
        Args:
            soup: BeautifulSoup object containing channel page
            channel_id: The ID of the channel
            
        Returns:
            dict: Structured channel bio data
        """
        try:
            if isinstance(soup, dict) and 'soup' in soup:
                soup = soup['soup']
                
            # Verify that we received a valid BS4 element    
            if not hasattr(soup, 'select_one'):
                config.logger.error(f"Invalid soup format for {channel_id}: not a BeautifulSoup element")
                return self._create_default_bio(channel_id)
                
            # Extract basic channel info with multiple selectors and fallbacks
            title = ""
            title_selectors = [
                '.etme_channel_info_header_title > span',
                '.channel_info_title',
                '.channel_title',
                'h1.title',
                '[class*="channel"][class*="title"]'
            ]
            
            for selector in title_selectors:
                title_elem = soup.select_one(selector)
                if title_elem and hasattr(title_elem, 'get_text'):
                    title = title_elem.get_text(strip=True)
                    if title:
                        break
                        
            # Extract username with fallbacks
            username = f"@{channel_id}"
            username_selectors = [
                '.etme_channel_info_header_username > a',
                '.channel_username',
                '.username',
                '[class*="channel"][class*="username"]'
            ]
            
            for selector in username_selectors:
                username_elem = soup.select_one(selector)
                if username_elem and hasattr(username_elem, 'get_text'):
                    extracted_username = username_elem.get_text(strip=True)
                    if extracted_username:
                        username = extracted_username
                        break
                        
            # Extract description with fallbacks
            description = ""
            desc_selectors = [
                '.etme_channel_info_description',
                '.channel_description',
                '.description',
                '[class*="channel"][class*="description"]'
            ]
            
            for selector in desc_selectors:
                desc_elem = soup.select_one(selector)
                if desc_elem and hasattr(desc_elem, 'get_text'):
                    description = desc_elem.get_text(strip=True)
                    if description:
                        break
            
            # Process counters with multiple approaches
            counters = {
                'follower_count': "0",
                'image_count': "0",
                'video_count': "0",
                'file_count': "0"
            }
            
            # Method 1: Standard counter extraction
            counter_selectors = [
                '.etme_channel_info_counters .etme_channel_info_counter',
                '.channel_counters .counter',
                '.counters .counter'
            ]
            
            for selector in counter_selectors:
                counter_elements = soup.select(selector)
                if counter_elements:
                    for counter in counter_elements:
                        try:
                            # Try to extract counter value and type
                            value_elem = counter.select_one('.counter_value') or counter.select_one('.value')
                            type_elem = counter.select_one('.counter_type') or counter.select_one('.type')
                            
                            if value_elem and type_elem:
                                value = value_elem.get_text(strip=True).replace('هزار', 'k')
                                counter_type = type_elem.get_text(strip=True)
                                
                                # Map counter types to our keys
                                if counter_type == 'دنبال‌کننده' or 'follower' in counter_type.lower():
                                    counters['follower_count'] = value
                                elif counter_type == 'عکس' or 'image' in counter_type.lower() or 'photo' in counter_type.lower():
                                    counters['image_count'] = value
                                elif counter_type == 'ویدیو' or 'video' in counter_type.lower():
                                    counters['video_count'] = value
                                elif counter_type == 'فایل' or 'file' in counter_type.lower():
                                    counters['file_count'] = value
                        except Exception as e:
                            config.logger.debug(f"Error extracting counter: {e}")
                    
                    # If we found counters, stop trying other selectors
                    if any(v != "0" for v in counters.values()):
                        break
            
            # Method 2: Look for specific counter elements directly
            if all(v == "0" for v in counters.values()):
                counter_mapping = {
                    'follower_count': ['.follower-count', '.subscribers', '[data-followers]'],
                    'image_count': ['.image-count', '.photos-count', '[data-photos]'],
                    'video_count': ['.video-count', '.videos-count', '[data-videos]'],
                    'file_count': ['.file-count', '.files-count', '[data-files]']
                }
                
                for counter_key, selectors in counter_mapping.items():
                    for selector in selectors:
                        try:
                            elem = soup.select_one(selector)
                            if elem:
                                if elem.get('data-count'):
                                    counters[counter_key] = elem.get('data-count')
                                elif hasattr(elem, 'get_text'):
                                    counters[counter_key] = elem.get_text(strip=True).replace('هزار', 'k')
                                break
                        except Exception as e:
                            config.logger.debug(f"Error extracting specific counter {counter_key}: {e}")
            
            # Build the structured bio dictionary
            return {
                "_": "channel",
                "channel_id": channel_id,
                "title": title,
                "username": username,
                "follower_count": counters.get("follower_count", "0"),
                "image_count": counters.get("image_count", "0"),
                "video_count": counters.get("video_count", "0"),
                "file_count": counters.get("file_count", "0"),
                "description": description,
                "crawled_at": datetime.now(self.tz).isoformat(),
                "extraction_errors": self._get_extraction_errors()
            }
        except Exception as e:
            config.logger.error(f"Unexpected error extracting channel bio for {channel_id}: {e}")
            return self._create_default_bio(channel_id)
    
    def _create_default_bio(self, channel_id):
        """Create a default bio when extraction fails"""
        return {
            "_": "channel",
            "channel_id": channel_id,
            "title": "",
            "username": f"@{channel_id}",
            "follower_count": "0",
            "image_count": "0",
            "video_count": "0",
            "file_count": "0",
            "description": "",
            "crawled_at": datetime.now(self.tz).isoformat(),
            "extraction_success": False,
            "extraction_errors": ["Failed to extract bio data"]
        } 