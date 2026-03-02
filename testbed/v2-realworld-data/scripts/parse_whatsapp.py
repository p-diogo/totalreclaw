#!/usr/bin/env python3
"""
WhatsApp Chat Parser
Parses WhatsApp chat export ZIP files and creates conversation chunks.
"""

import os
import re
import json
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional


class WhatsAppParser:
    """Parser for WhatsApp chat exports."""

    # Portuguese date format: DD/MM/YYYY, HH:MM:SS
    # Allow optional leading special characters (zero-width spaces, LTR marks, etc.)
    DATE_PATTERN = re.compile(r'^.*?\[(\d{2}/\d{2}/\d{4}),\s(\d{2}:\d{2}:\d{2})\]\s([^:]+):\s(.*)')

    def __init__(self, raw_dir: str, output_dir: str):
        self.raw_dir = Path(raw_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def parse_timestamp(self, date_str: str, time_str: str) -> datetime:
        """Parse Portuguese date format to datetime."""
        # DD/MM/YYYY, HH:MM:SS
        day, month, year = map(int, date_str.split('/'))
        hour, minute, second = map(int, time_str.split(':'))
        return datetime(year, month, day, hour, minute, second)

    def extract_chat_name(self, zip_filename: str) -> str:
        """Extract chat name from ZIP filename."""
        # Remove 'WhatsApp Chat - ' prefix and .zip extension
        name = zip_filename.replace('WhatsApp Chat - ', '').replace('.zip', '')
        return name

    def parse_chat_file(self, content: str, chat_name: str) -> List[Dict[str, Any]]:
        """Parse a single chat file and return messages."""
        messages = []
        lines = content.split('\n')

        current_message = None

        for line in lines:
            # Strip leading/trailing whitespace but preserve content
            original_line = line
            line = line.strip()

            if not line:
                continue

            # Check if this is a new message line
            match = self.DATE_PATTERN.match(line)

            if match:
                # Save previous message if exists
                if current_message:
                    messages.append(current_message)

                date_str, time_str, sender, content = match.groups()
                timestamp = self.parse_timestamp(date_str, time_str)

                # Skip encryption message
                if 'end-to-end encrypted' in content:
                    current_message = None
                    continue

                current_message = {
                    'timestamp': timestamp,
                    'sender': sender.strip(),
                    'content': content.strip(),
                    'chat_name': chat_name
                }
            elif current_message:
                # Check if this looks like a message embedded in another message
                # (happens with media placeholders with special characters)
                # Pattern: [DD/MM/YYYY, HH:MM:SS] Sender: content
                embedded_match = self.DATE_PATTERN.match(original_line.strip())
                if embedded_match:
                    # This is actually a new message that wasn't caught by strip()
                    # Save previous message
                    messages.append(current_message)

                    date_str, time_str, sender, content = embedded_match.groups()
                    timestamp = self.parse_timestamp(date_str, time_str)

                    # Skip encryption message
                    if 'end-to-end encrypted' not in content:
                        current_message = {
                            'timestamp': timestamp,
                            'sender': sender.strip(),
                            'content': content.strip(),
                            'chat_name': chat_name
                        }
                    else:
                        current_message = None
                else:
                    # Continuation of previous message (multi-line)
                    # Use original_line to preserve formatting
                    if current_message['content']:
                        current_message['content'] += '\n' + original_line.strip()
                    else:
                        current_message['content'] = original_line.strip()

        # Don't forget the last message
        if current_message:
            messages.append(current_message)

        return messages

    def filter_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter out unwanted messages (media placeholders, etc.)."""
        filtered = []

        # Remove control characters and check for media placeholders
        def clean_content(text: str) -> str:
            # Remove common invisible Unicode characters
            for char in ['\u200b', '\u200c', '\u200d', '\u200e', '\u200f', '\ufeff']:
                text = text.replace(char, '')
            return text

        # Patterns to identify media placeholder messages
        media_patterns = [
            r'\s*image\s+omitted\s*$',
            r'\s*video\s+omitted\s*$',
            r'\s*audio\s+omitted\s*$',
            r'\s*document\s+omitted\s*$',
            r'\s*sticker\s+omitted\s*$',
            r'\s*gif\s+omitted\s*$',
            r'\s*contact\s+omitted\s*$',
            r'\s*location\s+omitted\s*$',
            r'\s*poll\s+omitted\s*$',
            r'\s*ptt\s+omitted\s*$',
            r'\s*voice\s+omitted\s*$',
        ]

        # Compile regex patterns
        media_regex = [re.compile(p, re.IGNORECASE) for p in media_patterns]

        for msg in messages:
            content = msg['content']
            cleaned = clean_content(content)

            # Remove media placeholders from the end of lines
            for pattern in media_regex:
                cleaned = pattern.sub('', cleaned)

            cleaned = cleaned.strip()

            # Skip if message is now empty after cleaning
            if not cleaned:
                continue

            msg['content'] = cleaned
            filtered.append(msg)

        return filtered

    def create_chunks(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Create conversation chunks from messages."""
        if not messages:
            return []

        chunks = []
        current_chunk_messages = []
        current_chunk_content = []

        # Gap threshold for new chunk (1 hour)
        TIME_GAP_THRESHOLD = timedelta(hours=1)
        MIN_CHUNK_SIZE = 100  # characters
        MAX_CHUNK_SIZE = 1000  # characters

        for i, msg in enumerate(messages):
            msg_content = msg['content']

            # Check if we should start a new chunk
            should_start_new_chunk = False

            if current_chunk_messages:
                last_msg = current_chunk_messages[-1]
                time_gap = msg['timestamp'] - last_msg['timestamp']

                # Check time gap
                if time_gap > TIME_GAP_THRESHOLD:
                    should_start_new_chunk = True

                # Check max chunk size (but only if we have minimum content)
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
                current_chunk_content = []

            current_chunk_messages.append(msg)
            current_chunk_content.append(msg_content)

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
        chunk_id = f"wa_{chat_name}_{timestamp.strftime('%Y%m%d_%H%M')}"

        return {
            'id': chunk_id,
            'content': content,
            'source': 'whatsapp',
            'chat_name': chat_name,
            'participants': participants,
            'timestamp_start': timestamp_start,
            'timestamp_end': timestamp_end,
            'message_count': len(messages)
        }

    def process_zip(self, zip_path: Path) -> List[Dict[str, Any]]:
        """Process a single ZIP file."""
        chat_name = self.extract_chat_name(zip_path.name)
        chunks = []

        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_file:
                # Find _chat.txt file
                chat_files = [f for f in zip_file.namelist() if f.endswith('_chat.txt') or f.endswith('.txt')]

                if not chat_files:
                    print(f"Warning: No chat file found in {zip_path.name}")
                    return chunks

                # Read the first chat file found
                chat_file = chat_files[0]
                with zip_file.open(chat_file) as f:
                    # Try to read with UTF-8, fallback to latin-1 for Portuguese
                    try:
                        content = f.read().decode('utf-8')
                    except UnicodeDecodeError:
                        f.seek(0)
                        content = f.read().decode('latin-1')

                # Parse messages
                messages = self.parse_chat_file(content, chat_name)

                # Filter out media placeholders
                messages = self.filter_messages(messages)

                # Create chunks
                chunks = self.create_chunks(messages)

                print(f"Processed {chat_name}: {len(messages)} messages -> {len(chunks)} chunks")

        except Exception as e:
            print(f"Error processing {zip_path.name}: {e}")

        return chunks

    def process_all(self) -> Dict[str, Any]:
        """Process all WhatsApp ZIP files."""
        all_chunks = []
        total_messages = 0
        chats_processed = 0

        # Find all ZIP files
        zip_files = list(self.raw_dir.glob('*.zip'))

        if not zip_files:
            print(f"No ZIP files found in {self.raw_dir}")
            return self._create_output([], 0, 0)

        for zip_path in sorted(zip_files):
            chunks = self.process_zip(zip_path)
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
                'source': 'whatsapp',
                'total_memories': len(chunks),
                'total_messages': total_messages,
                'chats_processed': chats_processed
            }
        }

    def save_output(self, data: Dict[str, Any], filename: str = 'whatsapp_memories.json'):
        """Save the output to a JSON file."""
        output_path = self.output_dir / filename

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"Saved {len(data['memories'])} memories to {output_path}")
        return output_path


def main():
    """Main entry point."""
    # Get script directory
    script_dir = Path(__file__).parent.parent

    raw_dir = script_dir / 'raw' / 'whatsapp'
    output_dir = script_dir / 'processed'

    parser = WhatsAppParser(str(raw_dir), str(output_dir))
    result = parser.process_all()
    parser.save_output(result)

    # Print summary
    print(f"\nSummary:")
    print(f"  Chats processed: {result['metadata']['chats_processed']}")
    print(f"  Total messages: {result['metadata']['total_messages']}")
    print(f"  Total memories: {result['metadata']['total_memories']}")


if __name__ == '__main__':
    main()
