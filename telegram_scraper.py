import asyncio
import json
import time
import nest_asyncio
from telethon import TelegramClient
from telethon.tl.types import PeerChannel, PeerUser, PeerChat
from telethon.errors import FloodWaitError, SessionPasswordNeededError
import threading
from collections import deque

nest_asyncio.apply()

class OptimizedTelegramScraper:
    def __init__(self, api_id, api_hash):
        self.client = TelegramClient('session_name', api_id, api_hash)
        self.user_cache = {}
        self.cache_lock = threading.Lock()
        self.rate_limiter = deque(maxlen=100)
        self.stats = {"total": 0, "with_media": 0, "with_text": 0, "users_found": 0, "self_deletions": 0}

    async def login(self):
        print("Connecting...")
        await self.client.connect()
        if not await self.client.is_user_authorized():
            print("First-time login. Please enter your phone number.")
            phone = input("Enter phone (e.g., +1234567890): ")
            await self.client.send_code_request(phone)
            try:
                await self.client.sign_in(phone, input("Enter the code you received: "))
            except SessionPasswordNeededError:
                await self.client.sign_in(password=input("Enter your 2FA password: "))
            print("Login successful!")
        else:
            print("Already logged in.")

    async def smart_rate_limit(self):
        now = time.time()
        while self.rate_limiter and now - self.rate_limiter[0] > 60:
            self.rate_limiter.popleft()

        if len(self.rate_limiter) > 90:
            await asyncio.sleep(0.8)
        elif len(self.rate_limiter) > 60:
            await asyncio.sleep(0.3)
        else:
            await asyncio.sleep(0.05)
        self.rate_limiter.append(now)

    async def batch_get_user_info(self, user_ids):
        results = {}
        to_fetch = []

        with self.cache_lock:
            for user_id in user_ids:
                if user_id in self.user_cache:
                    results[user_id] = self.user_cache[user_id]
                else:
                    to_fetch.append(user_id)

        batch_size = 10
        for i in range(0, len(to_fetch), batch_size):
            batch = to_fetch[i:i + batch_size]
            tasks = [self.get_single_user_info(user_id) for user_id in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            for user_id, result in zip(batch, batch_results):
                if not isinstance(result, Exception):
                    with self.cache_lock:
                        self.user_cache[user_id] = result
                    results[user_id] = result
                else:
                    results[user_id] = {"id": user_id, "error": str(result)}
            await self.smart_rate_limit()
        return results

    async def get_single_user_info(self, user_id):
        try:
            if not user_id:
                return None
            try:
                user = await self.client.get_entity(PeerUser(user_id))
            except:
                user = await self.client.get_entity(user_id)

            return {
                "id": user.id,
                "username": getattr(user, 'username', None),
                "first_name": getattr(user, 'first_name', None),
                "last_name": getattr(user, 'last_name', None),
                "phone": getattr(user, 'phone', None),
                "is_bot": getattr(user, 'bot', False),
                "is_channel": hasattr(user, 'broadcast')
            }
        except FloodWaitError as e:
            print(f"Rate limited for {e.seconds} seconds on user {user_id}")
            await asyncio.sleep(e.seconds)
            return await self.get_single_user_info(user_id)
        except Exception as e:
            return {"id": user_id, "error": str(e)}

    async def extract_sender_info_fast(self, old_message, admin_log_event):
        sender_id = None
        if hasattr(old_message, 'from_id') and old_message.from_id:
            if hasattr(old_message.from_id, 'user_id'):
                sender_id = old_message.from_id.user_id
            elif hasattr(old_message.from_id, 'channel_id'):
                sender_id = old_message.from_id.channel_id
            elif isinstance(old_message.from_id, int):
                sender_id = old_message.from_id
        if not sender_id and hasattr(old_message, 'sender_id'):
            sender_id = old_message.sender_id
        if not sender_id and hasattr(admin_log_event, 'user_id'):
            sender_id = admin_log_event.user_id
        return sender_id

    async def process_messages_batch(self, events_batch):
        results = []
        user_ids_to_fetch = set()
        event_data = []

        for event in events_batch:
            if event.deleted_message and event.old:
                original_sender_id = await self.extract_sender_info_fast(event.old, event)
                admin_id = getattr(event, 'user_id', None)
                event_info = {
                    'event': event,
                    'original_sender_id': original_sender_id,
                    'admin_id': admin_id
                }
                event_data.append(event_info)
                if original_sender_id:
                    user_ids_to_fetch.add(original_sender_id)
                if admin_id:
                    user_ids_to_fetch.add(admin_id)

        user_infos = await self.batch_get_user_info(list(user_ids_to_fetch)) if user_ids_to_fetch else {}

        for info in event_data:
            event = info['event']
            original_sender_id = info['original_sender_id']
            admin_id = info['admin_id']
            msg_data = {
                "id": event.old.id,
                "date": event.old.date.isoformat(),
                "text": getattr(event.old, "message", None),
                "has_media": bool(event.old.media),
                "media_type": str(type(event.old.media).__name__) if event.old.media else None,
                "original_sender": {
                    "user_id": original_sender_id,
                    "user_info": user_infos.get(original_sender_id)
                },
                "deleted_by": {
                    "admin_id": admin_id,
                    "admin_info": user_infos.get(admin_id)
                },
                "action_date": event.date.isoformat(),
                "is_self_deletion": original_sender_id == admin_id if original_sender_id and admin_id else False,
            }
            results.append(msg_data)

            self.stats["total"] += 1
            if msg_data["text"]:
                self.stats["with_text"] += 1
            if msg_data["has_media"]:
                self.stats["with_media"] += 1
            if original_sender_id:
                self.stats["users_found"] += 1
            if msg_data["is_self_deletion"]:
                self.stats["self_deletions"] += 1
        return results

    async def enhanced_message_scraper(self, target_channel):
        try:
            group = await self.client.get_entity(target_channel)
            print(f"Target: {group.title} (ID: {group.id})")

            all_results = []
            print("Pre-caching participants...")
            try:
                participant_count = 0
                async for participant in self.client.iter_participants(group, limit=500):
                    self.user_cache[participant.id] = {
                        "id": participant.id,
                        "username": getattr(participant, 'username', None),
                        "first_name": getattr(participant, 'first_name', None),
                        "last_name": getattr(participant, 'last_name', None),
                        "is_bot": getattr(participant, 'bot', False)
                    }
                    participant_count += 1
                print(f"Cached {participant_count} participants")
            except Exception as e:
                print(f"Could not cache all participants: {e}")

            print("Starting optimized batch processing...")
            batch_size = 20
            events_batch = []

            async for event in self.client.iter_admin_log(group, delete=True):
                events_batch.append(event)
                if len(events_batch) >= batch_size:
                    batch_results = await self.process_messages_batch(events_batch)
                    all_results.extend(batch_results)
                    print(f"Processed {self.stats['total']} messages...")
                    events_batch = []
                    await self.smart_rate_limit()

            if events_batch:
                batch_results = await self.process_messages_batch(events_batch)
                all_results.extend(batch_results)

            output_file = f"deleted_messages_optimized_{group.id}.json"
            output_data = {
                "metadata": {
                    "channel_id": group.id,
                    "channel_title": group.title,
                    "scrape_date": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "statistics": self.stats,
                    "unique_users": len(self.user_cache),
                    "extraction_method": "optimized_batch_v3"
                },
                "user_cache": self.user_cache,
                "messages": all_results
            }

            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(output_data, f, ensure_ascii=False, indent=2)

            print(f"\n--- Report Saved: {output_file} ---")
            print(f"Final Results:")
            print(f"  - Total messages processed: {self.stats['total']}")
            print(f"  - Users identified: {self.stats['users_found']}")
            print(f"  - Cached users: {len(self.user_cache)}")

        except Exception as e:
            print(f"Error occurred: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await self.client.disconnect()
            print("Disconnected from Telegram.")

async def main():
    print("--- Optimized Telegram Deleted Message Scraper ---")
    print("You will need your API credentials from my.telegram.org\n")
    
    api_id = input("Enter your API ID: ")
    api_hash = input("Enter your API Hash: ")

    scraper = OptimizedTelegramScraper(api_id, api_hash)
    await scraper.login()

    target_channel = input("\nEnter the target channel ID (e.g., -100123...) or username (e.g., @channel): ")
    
    await scraper.enhanced_message_scraper(target_channel)

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())
