#!/usr/bin/env python3
"""
Telegram Chat Parser
Parses Telegram chat export JSON files and creates conversation chunks.
Supports JSON format from Telegram Desktop export.
"""

import os
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional


class TelegramParser:
    """Parser for Telegram chat exports."""

    def __init__(self, raw_dir: str, output_dir: str):
        self.raw_dir = Path(raw_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def parse_timestamp(self, timestamp_str: str) -> datetime:
        """Parse Telegram timestamp to datetime."""
        # Telegram uses ISO 8601 format: "2024-01-15T10:30:00"
        try:
            # Remove timezone info if present and parse
            if 'T' in timestamp_str:
                return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00').split('+')[0])
            else:
                return datetime.fromisoformat(timestamp_str)
        except ValueError:
            # Fallback for different formats
            for fmt in ('%Y-%m-%d', '%Y-%m-%d %H:%M:%S', '%d.%m.%Y'):
                try:
                    return datetime.strptime(timestamp_str.split()[0], fmt)
                except ValueError:
                    continue
            raise ValueError(f"Cannot parse timestamp: {timestamp_str}")

    def extract_text(self, text_field: Any) -> Optional[str]:
        """Extract text from Telegram text field (can be string or array)."""
        if text_field is None:
            return None

        if isinstance(text_field, str):
            return text_field

        if isinstance(text_field, list):
            # Telegram exports text as array of strings/objects
            text_parts = []
            for item in text_field:
                if isinstance(item, str):
                    text_parts.append(item)
                elif isinstance(item, dict):
                    # Handle rich text elements
                    if 'text' in item:
                        text_parts.append(item['text'])
                    elif 'type' in item:
                        # Handle different text entity types
                        entity_type = item.get('type', '')
                        if entity_type == 'link':
                            text_parts.append(item.get('text', ''))
                        elif entity_type == 'plain':
                            text_parts.append(item.get('text', ''))
            return ' '.join(text_parts) if text_parts else None

        return str(text_field)

    def get_sender_name(self, message: Dict[str, Any], chat_name: str) -> str:
        """Extract sender name from message."""
        # Try different fields for sender
        if 'from' in message and message['from']:
            if isinstance(message['from'], str):
                return message['from']
            elif isinstance(message['from'], dict):
                return message['from'].get('name', message['from'].get('id', 'Unknown'))

        if 'from_id' in message:
            from_id = message['from_id']
            if isinstance(from_id, str):
                return from_id.split('_')[-1] if '_' in from_id else from_id

        # Check if it's a message from the current user
        if message.get('out', False):
            return 'Me'

        # Default to chat name for incoming messages
        return chat_name

    def parse_message(self, message: Dict[str, Any], chat_name: str) -> Optional[Dict[str, Any]]:
        """Parse a single Telegram message."""
        # Skip messages without content
        if 'text' not in message and 'media' not in message and 'media_type' not in message:
            return None

        # Extract text content
        text_content = self.extract_text(message.get('text'))

        # Handle media messages
        media_type = None
        media_description = None

        # Check for media in different possible fields
        media = message.get('media') or message.get('media_type')

        if media:
            if isinstance(media, str):
                media_type = media
            elif isinstance(media, dict):
                media_type = media.get('type', 'unknown')

            # Create description for media
            if media_type == 'sticker':
                media_description = '[Sticker]'
            elif media_type == 'image':
                media_description = '[Image]'
            elif media_type == 'video':
                media_description = '[Video]'
            elif media_type == 'audio':
                media_description = '[Audio]'
            elif media_type == 'voice':
                media_description = '[Voice message]'
            elif media_type == 'document':
                media_description = '[Document]'
            elif media_type == 'gif':
                media_description = '[GIF]'
            elif media_type == 'location':
                media_description = '[Location]'
            elif media_type == 'webpage':
                media_description = '[Link preview]'
            else:
                media_description = f'[{media_type.capitalize() if media_type else "Media"}]'

        # Combine text and media description
        content_parts = []
        if text_content:
            content_parts.append(text_content)
        if media_description:
            content_parts.append(media_description)

        if not content_parts:
            return None

        content = ' '.join(content_parts)

        # Parse timestamp
        timestamp_str = message.get('date', message.get('date_unixtime', ''))
        try:
            timestamp = self.parse_timestamp(timestamp_str)
        except (ValueError, TypeError):
            return None

        # Get sender name
        sender = self.get_sender_name(message, chat_name)

        return {
            'timestamp': timestamp,
            'sender': sender,
            'content': content,
            'chat_name': chat_name,
            'media_type': media_type
        }

    def parse_chat_file(self, chat_data: Dict[str, Any], chat_name: str) -> List[Dict[str, Any]]:
        """Parse a single chat file and return messages."""
        messages = []

        # Telegram exports have different structures
        # Try to find messages array
        messages_data = None

        if 'messages' in chat_data:
            messages_data = chat_data['messages']
        elif 'chats' in chat_data and isinstance(chat_data['chats'], list):
            # Find messages in chat list
            for chat in chat_data['chats']:
                if 'messages' in chat:
                    messages_data = chat['messages']
                    break

        if not messages_data:
            print(f"Warning: No messages found in {chat_name}")
            return messages

        # Parse each message
        for msg in messages_data:
            parsed_msg = self.parse_message(msg, chat_name)
            if parsed_msg:
                messages.append(parsed_msg)

        # Sort by timestamp
        messages.sort(key=lambda m: m['timestamp'])

        return messages

    def filter_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter out unwanted messages (service messages, etc.)."""
        filtered = []

        # Patterns to filter out
        service_patterns = [
            'created the group',
            'changed the group name',
            'added',
            'removed',
            'left the group',
            'joined the group',
            'pinned a message',
            'unpinned a message',
            'changed the chat photo',
            'deleted the chat photo'
        ]

        for msg in messages:
            content = msg['content'].strip().lower()

            # Skip service messages
            if any(pattern in content for pattern in service_patterns):
                continue

            # Skip empty messages after stripping media
            if content in ('[image]', '[video]', '[audio]', '[sticker]', '[gif]', '[link preview]'):
                continue

            filtered.append(msg)

        return filtered

    def create_chunks(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Create conversation chunks from messages."""
        if not messages:
            return []

        chunks = []
        current_chunk_messages = []

        # Gap threshold for new chunk (1 hour)
        TIME_GAP_THRESHOLD = timedelta(hours=1)
        MIN_CHUNK_SIZE = 100  # characters
        MAX_CHUNK_SIZE = 1000  # characters

        for msg in messages:
            msg_content = msg['content']

            # Check if we should start a new chunk
            should_start_new_chunk = False

            if current_chunk_messages:
                last_msg = current_chunk_messages[-1]
                time_gap = msg['timestamp'] - last_msg['timestamp']

                # Check time gap
                if time_gap > TIME_GAP_THRESHOLD:
                    should_start_new_chunk = True

                # Check max chunk size
                current_size = sum(len(m['content']) for m in current_chunk_messages)
                if current_size + len(msg_content) > MAX_CHUNK_SIZE and current_size >= MIN_CHUNK_SIZE:
                    should_start_new_chunk = True

            if should_start_new_chunk:
                # Save current chunk if it meets minimum size
                chunk_text = '\n'.join(m['content'] for m in current_chunk_messages)
                if len(chunk_text) >= MIN_CHUNK_SIZE:
                    chunks.append(self._create_chunk_dict(current_chunk_messages))

                # Start new chunk
                current_chunk_messages = []

            current_chunk_messages.append(msg)

        # Don't forget the last chunk
        if current_chunk_messages:
            chunk_text = '\n'.join(m['content'] for m in current_chunk_messages)
            if len(chunk_text) >= MIN_CHUNK_SIZE:
                chunks.append(self._create_chunk_dict(current_chunk_messages))

        return chunks

    def _create_chunk_dict(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create a chunk dictionary from a list of messages."""
        # Get unique participants
        participants = sorted(set(m['sender'] for m in messages))

        # Format timestamps
        timestamp_start = messages[0]['timestamp'].isoformat()
        timestamp_end = messages[-1]['timestamp'].isoformat()

        # Combine message contents
        content_parts = []
        for msg in messages:
            sender = msg['sender']
            text = msg['content']
            content_parts.append(f"{sender}: {text}")

        content = '\n'.join(content_parts)

        # Create chunk ID
        chat_name = messages[0]['chat_name']
        timestamp = messages[0]['timestamp']
        # Sanitize chat name for ID
        safe_chat_name = ''.join(c if c.isalnum() or c in ('_', '-') else '_' for c in chat_name)
        chunk_id = f"tg_{safe_chat_name}_{timestamp.strftime('%Y%m%d_%H%M')}"

        return {
            'id': chunk_id,
            'content': content,
            'source': 'telegram',
            'chat_name': chat_name,
            'participants': participants,
            'timestamp_start': timestamp_start,
            'timestamp_end': timestamp_end,
            'message_count': len(messages)
        }

    def process_json_file(self, json_path: Path) -> List[Dict[str, Any]]:
        """Process a single JSON file."""
        chunks = []

        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Extract chat name from filename
            chat_name = json_path.stem.replace('result', '').replace('export', '').strip()
            if not chat_name:
                chat_name = json_path.stem

            # If the JSON has a name field, use it
            if isinstance(data, dict) and 'name' in data:
                chat_name = data['name']

            # Parse messages
            messages = self.parse_chat_file(data, chat_name)

            # Filter service messages
            messages = self.filter_messages(messages)

            # Create chunks
            chunks = self.create_chunks(messages)

            print(f"Processed {chat_name}: {len(messages)} messages -> {len(chunks)} chunks")

        except json.JSONDecodeError as e:
            print(f"Error parsing JSON in {json_path.name}: {e}")
        except Exception as e:
            print(f"Error processing {json_path.name}: {e}")

        return chunks

    def process_result_json(self, json_path: Path) -> List[Dict[str, Any]]:
        """
        Process a Telegram result.json file which may contain multiple chats.
        This is the default format from Telegram Desktop export.
        """
        all_chunks = []

        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Handle different export structures
            chats_to_process = []

            if 'chats' in data and isinstance(data['chats'], list):
                # Individual chats in a list
                chats_to_process = data['chats']
            elif 'messages' in data:
                # Single chat with messages
                chat_name = data.get('name', json_path.stem)
                chats_to_process = [{'name': chat_name, 'messages': data['messages']}]
            else:
                # Assume the whole file is one chat
                chat_name = data.get('name', json_path.stem)
                chats_to_process = [data]

            for chat_data in chats_to_process:
                if not isinstance(chat_data, dict):
                    continue

                chat_name = chat_data.get('name', json_path.stem)

                # Parse messages
                messages = self.parse_chat_file(chat_data, chat_name)

                # Filter service messages
                messages = self.filter_messages(messages)

                # Create chunks
                chunks = self.create_chunks(messages)
                all_chunks.extend(chunks)

                print(f"Processed {chat_name}: {len(messages)} messages -> {len(chunks)} chunks")

        except json.JSONDecodeError as e:
            print(f"Error parsing JSON in {json_path.name}: {e}")
        except Exception as e:
            print(f"Error processing {json_path.name}: {e}")

        return all_chunks

    def process_all(self) -> Dict[str, Any]:
        """Process all Telegram JSON files."""
        all_chunks = []
        total_messages = 0
        chats_processed = 0

        # Find all JSON files
        json_files = list(self.raw_dir.rglob('*.json'))

        if not json_files:
            print(f"No JSON files found in {self.raw_dir}")
            # Try to process sample data
            return self._create_sample_output()

        # Check for result.json (Telegram Desktop export format)
        result_json = self.raw_dir / 'result.json'
        if result_json.exists():
            chunks = self.process_result_json(result_json)
            all_chunks.extend(chunks)
            chats_processed += 1
        else:
            # Process individual JSON files (including sample for testing)
            for json_path in sorted(json_files):
                # Only skip sample if we have other files
                if json_path.name == 'sample_telegram.json' and len(json_files) > 1:
                    continue  # Skip sample file when processing real data

                chunks = self.process_json_file(json_path)
                all_chunks.extend(chunks)
                chats_processed += 1

        # Calculate total messages
        for chunk in all_chunks:
            total_messages += chunk['message_count']

        return self._create_output(all_chunks, total_messages, chats_processed)

    def _create_output(self, chunks: List[Dict[str, Any]], total_messages: int, chats_processed: int) -> Dict[str, Any]:
        """Create the output dictionary."""
        return {
            'memories': chunks,
            'metadata': {
                'source': 'telegram',
                'total_memories': len(chunks),
                'total_messages': total_messages,
                'chats_processed': chats_processed
            }
        }

    def _create_sample_output(self) -> Dict[str, Any]:
        """Create sample output for testing when no real data is available."""
        # Create sample messages
        from datetime import datetime, timedelta

        base_time = datetime(2024, 1, 15, 10, 0, 0)

        sample_messages = [
            {
                'timestamp': base_time,
                'sender': 'Alice',
                'content': 'Hey! Are we still on for lunch tomorrow?',
                'chat_name': 'Friends Group'
            },
            {
                'timestamp': base_time + timedelta(minutes=5),
                'sender': 'Bob',
                'content': 'Yes! Should we meet at that Italian place?',
                'chat_name': 'Friends Group'
            },
            {
                'timestamp': base_time + timedelta(minutes=10),
                'sender': 'Me',
                'content': 'Sounds good. What time works for everyone?',
                'chat_name': 'Friends Group'
            },
            {
                'timestamp': base_time + timedelta(minutes=15),
                'sender': 'Alice',
                'content': 'How about 1pm?',
                'chat_name': 'Friends Group'
            },
            {
                'timestamp': base_time + timedelta(minutes=20),
                'sender': 'Bob',
                'content': 'Perfect, see you all there!',
                'chat_name': 'Friends Group'
            }
        ]

        chunks = self.create_chunks(sample_messages)

        return self._create_output(chunks, len(sample_messages), 1)

    def save_output(self, data: Dict[str, Any], filename: str = 'telegram_memories.json'):
        """Save the output to a JSON file."""
        output_path = self.output_dir / filename

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"Saved {len(data['memories'])} memories to {output_path}")
        return output_path

    def create_sample_data(self):
        """Create a sample Telegram export for testing."""
        base_time = datetime(2024, 1, 15, 10, 0, 0)

        sample_data = {
            "name": "Friends Group",
            "type": "group",
            "id": 1234567890,
            "messages": [
                {
                    "id": 1,
                    "type": "message",
                    "date": base_time.isoformat(),
                    "from": "Alice",
                    "from_id": "user123",
                    "text": "Hey! Are we still on for lunch tomorrow?",
                    "out": False
                },
                {
                    "id": 2,
                    "type": "message",
                    "date": (base_time + timedelta(minutes=5)).isoformat(),
                    "from": "Bob",
                    "from_id": "user456",
                    "text": "Yes! Should we meet at that Italian place?",
                    "out": False
                },
                {
                    "id": 3,
                    "type": "message",
                    "date": (base_time + timedelta(minutes=10)).isoformat(),
                    "from": "Me",
                    "from_id": "user789",
                    "text": "Sounds good. What time works for everyone?",
                    "out": True
                },
                {
                    "id": 4,
                    "type": "message",
                    "date": (base_time + timedelta(minutes=15)).isoformat(),
                    "from": "Alice",
                    "from_id": "user123",
                    "text": "How about 1pm?",
                    "out": False
                },
                {
                    "id": 5,
                    "type": "message",
                    "date": (base_time + timedelta(minutes=20)).isoformat(),
                    "from": "Bob",
                    "from_id": "user456",
                    "text": "Perfect, see you all there!",
                    "out": False
                },
                {
                    "id": 6,
                    "type": "message",
                    "date": (base_time + timedelta(hours=2)).isoformat(),
                    "from": "Charlie",
                    "from_id": "user999",
                    "text": ["Don't forget to bring the presentation files!"],
                    "out": False
                },
                {
                    "id": 7,
                    "type": "message",
                    "date": (base_time + timedelta(hours=2, minutes=5)).isoformat(),
                    "from": "Me",
                    "from_id": "user789",
                    "text": "Already have them on my laptop. See you all!",
                    "out": True
                },
                {
                    "id": 8,
                    "type": "message",
                    "date": (base_time + timedelta(days=1, hours=10)).isoformat(),
                    "from": "Alice",
                    "from_id": "user123",
                    "media": "image",
                    "text": "The food was amazing!",
                    "out": False
                },
                {
                    "id": 9,
                    "type": "service",
                    "date": (base_time + timedelta(days=1, hours=10, minutes=5)).isoformat(),
                    "from": "Bob",
                    "from_id": "user456",
                    "text": "Bob created the group",
                    "out": False
                },
                {
                    "id": 10,
                    "type": "message",
                    "date": (base_time + timedelta(days=1, hours=12)).isoformat(),
                    "from": "Me",
                    "from_id": "user789",
                    "text": "Let's do this again next week!",
                    "out": True
                }
            ]
        }

        sample_path = self.raw_dir / 'sample_telegram.json'
        with open(sample_path, 'w', encoding='utf-8') as f:
            json.dump(sample_data, f, ensure_ascii=False, indent=2)

        print(f"Created sample Telegram export at {sample_path}")
        return sample_path


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description='Parse Telegram chat exports')
    parser.add_argument('--input', '-i', help='Input directory with Telegram exports')
    parser.add_argument('--output', '-o', help='Output directory for processed data')
    parser.add_argument('--create-sample', action='store_true', help='Create sample data for testing')

    args = parser.parse_args()

    # Get script directory
    script_dir = Path(__file__).parent.parent

    if args.input:
        raw_dir = Path(args.input)
    else:
        raw_dir = script_dir / 'raw' / 'telegram'

    if args.output:
        output_dir = Path(args.output)
    else:
        output_dir = script_dir / 'processed'

    telegram_parser = TelegramParser(str(raw_dir), str(output_dir))

    # Create sample data if requested
    if args.create_sample:
        telegram_parser.create_sample_data()

    # Process all Telegram exports
    result = telegram_parser.process_all()
    telegram_parser.save_output(result)

    # Print summary
    print(f"\nSummary:")
    print(f"  Chats processed: {result['metadata']['chats_processed']}")
    print(f"  Total messages: {result['metadata']['total_messages']}")
    print(f"  Total memories: {result['metadata']['total_memories']}")


if __name__ == '__main__':
    main()
