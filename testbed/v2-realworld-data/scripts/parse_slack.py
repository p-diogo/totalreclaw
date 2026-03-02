#!/usr/bin/env python3
"""
Slack Chat Parser
Parses anonymized Slack export JSON files and creates conversation chunks.

Follows the same pattern as parse_whatsapp.py for consistency.

Usage:
    python parse_slack.py [input_dir] [output_dir]

Example:
    python parse_slack.py ./raw/slack/ ./processed/
"""

import os
import re
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional
from collections import defaultdict


class SlackParser:
    """Parser for anonymized Slack export data."""

    def __init__(self, raw_dir: str, output_dir: str):
        self.raw_dir = Path(raw_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Chunking parameters (same as WhatsApp parser)
        self.TIME_GAP_THRESHOLD = timedelta(hours=1)
        self.MIN_CHUNK_SIZE = 100  # characters
        self.MAX_CHUNK_SIZE = 1000  # characters

        # Statistics
        self.stats = {
            'channels_processed': 0,
            'total_messages': 0,
            'total_chunks': 0,
            'threads_processed': 0,
        }

    def parse_timestamp(self, ts: str) -> datetime:
        """Parse Slack timestamp (Unix epoch with microseconds)."""
        try:
            # Slack timestamps are like "1735827759.060029"
            seconds, microseconds = ts.split('.')
            return datetime.fromtimestamp(int(seconds) + int(microseconds) / 1_000_000)
        except (ValueError, AttributeError):
            # Fallback for malformed timestamps
            return datetime.now()

    def load_messages_from_channel(self, channel_dir: Path) -> List[Dict[str, Any]]:
        """Load all messages from a channel directory."""
        messages = []
        json_files = sorted(channel_dir.glob('*.json'))

        for json_file in json_files:
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    file_messages = json.load(f)

                if isinstance(file_messages, list):
                    messages.extend(file_messages)

            except Exception as e:
                print(f"Error loading {json_file}: {e}")

        return messages

    def filter_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter out system messages and empty content."""
        filtered = []

        # Skip these subtypes (system messages, bot messages, etc.)
        skip_subtypes = {
            'channel_join', 'channel_leave', 'channel_topic', 'channel_purpose',
            'channel_name', 'channel_archive', 'channel_unarchive',
            'bot_message', 'bot_add', 'bot_remove',
            'file_share', 'file_comment', 'file_mention',
            'pinned_item', 'unpinned_item',
            'reminder_add', 'reminder_delete',
            'slackbot_response', 'tombstone', 'hide_reply',
        }

        for msg in messages:
            # Skip system messages by subtype
            subtype = msg.get('subtype')
            if subtype in skip_subtypes:
                continue

            # Skip messages without user (usually system messages)
            if 'user' not in msg:
                continue

            # Skip empty messages
            text = msg.get('text', '').strip()
            if not text:
                continue

            # Skip deleted messages
            if text == 'This message was deleted.' or 'This content has been deleted' in text:
                continue

            # Skip messages that are only URL removals
            if text == '<URL_REMOVED>' or text == '[EMAIL_REMOVED]':
                continue

            filtered.append(msg)

        return filtered

    def group_threads(self, messages: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """Group messages by thread. Non-thread messages go to 'main'."""
        threads = defaultdict(list)
        main_messages = []

        # First pass: identify thread parents and replies
        thread_parents = {}  # thread_ts -> parent message

        for msg in messages:
            thread_ts = msg.get('thread_ts')

            if thread_ts:
                # This is part of a thread
                if msg.get('ts') == thread_ts:
                    # This is the thread parent
                    thread_parents[thread_ts] = msg
                threads[thread_ts].append(msg)
            else:
                # Not part of a thread
                main_messages.append(msg)

        # Sort each thread by timestamp
        for thread_ts in threads:
            threads[thread_ts].sort(key=lambda m: m.get('ts', ''))

        return threads, main_messages

    def format_message_content(self, msg: Dict[str, Any]) -> str:
        """Format a message for chunk content."""
        user = msg.get('user', 'unknown_user')
        text = msg.get('text', '').strip()

        # Clean up text
        # Remove remaining URL artifacts but keep readable text
        text = re.sub(r'<URL_REMOVED>', '', text)
        text = re.sub(r'\[EMAIL_REMOVED\]', '', text)
        text = text.strip()

        if not text:
            return ''

        return f"{user}: {text}"

    def create_chunk(self, messages: List[Dict[str, Any]], channel_name: str,
                     thread_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Create a chunk dictionary from a list of messages."""
        if not messages:
            return None

        # Format message contents
        content_parts = []
        for msg in messages:
            formatted = self.format_message_content(msg)
            if formatted:
                content_parts.append(formatted)

        if not content_parts:
            return None

        content = '\n'.join(content_parts)

        # Check minimum size
        if len(content) < self.MIN_CHUNK_SIZE:
            return None

        # Get unique participants
        participants = sorted(set(msg.get('user', 'unknown') for msg in messages))

        # Parse timestamps
        timestamps = [self.parse_timestamp(msg['ts']) for msg in messages if msg.get('ts')]
        if not timestamps:
            return None

        timestamp_start = min(timestamps)
        timestamp_end = max(timestamps)

        # Create chunk ID
        if thread_id:
            chunk_id = f"slack_{channel_name}_thread_{thread_id.replace('.', '_')}"
        else:
            chunk_id = f"slack_{channel_name}_{timestamp_start.strftime('%Y%m%d_%H%M')}"

        return {
            'id': chunk_id,
            'content': content,
            'source': 'slack',
            'channel_name': channel_name,
            'participants': participants,
            'timestamp_start': timestamp_start.isoformat(),
            'timestamp_end': timestamp_end.isoformat(),
            'message_count': len(messages),
            'is_thread': thread_id is not None
        }

    def chunk_thread(self, messages: List[Dict[str, Any]], channel_name: str,
                     thread_ts: str) -> List[Dict[str, Any]]:
        """Create chunks from a thread. Threads are kept together when possible."""
        chunks = []

        # Sort by timestamp
        messages = sorted(messages, key=lambda m: m.get('ts', ''))

        # Try to keep entire thread as one chunk if it fits
        chunk = self.create_chunk(messages, channel_name, thread_ts)
        if chunk:
            chunks.append(chunk)
            return chunks

        # If thread is too large, split it
        current_messages = []
        current_size = 0

        for msg in messages:
            msg_text = self.format_message_content(msg)
            msg_size = len(msg_text)

            # Check if adding this message would exceed max size
            if current_messages and current_size + msg_size > self.MAX_CHUNK_SIZE:
                # Save current chunk if it meets minimum size
                if current_size >= self.MIN_CHUNK_SIZE:
                    chunk = self.create_chunk(current_messages, channel_name, thread_ts)
                    if chunk:
                        chunks.append(chunk)

                # Start new chunk
                current_messages = []
                current_size = 0

            current_messages.append(msg)
            current_size += msg_size + 1  # +1 for newline

        # Don't forget the last chunk
        if current_messages and current_size >= self.MIN_CHUNK_SIZE:
            chunk = self.create_chunk(current_messages, channel_name, thread_ts)
            if chunk:
                chunks.append(chunk)

        return chunks

    def chunk_main_messages(self, messages: List[Dict[str, Any]], channel_name: str) -> List[Dict[str, Any]]:
        """Create chunks from main (non-thread) messages using time gaps."""
        chunks = []

        # Sort by timestamp
        messages = sorted(messages, key=lambda m: m.get('ts', ''))

        current_messages = []
        current_size = 0

        for i, msg in enumerate(messages):
            msg_text = self.format_message_content(msg)
            msg_size = len(msg_text)

            if not msg_text:
                continue

            # Check if we should start a new chunk
            should_start_new_chunk = False

            if current_messages:
                last_msg = current_messages[-1]
                last_ts = self.parse_timestamp(last_msg['ts'])
                current_ts = self.parse_timestamp(msg['ts'])
                time_gap = current_ts - last_ts

                # Check time gap
                if time_gap > self.TIME_GAP_THRESHOLD:
                    should_start_new_chunk = True

                # Check max chunk size
                if current_size + msg_size > self.MAX_CHUNK_SIZE and current_size >= self.MIN_CHUNK_SIZE:
                    should_start_new_chunk = True

            if should_start_new_chunk:
                # Save current chunk
                chunk = self.create_chunk(current_messages, channel_name)
                if chunk:
                    chunks.append(chunk)

                # Start new chunk
                current_messages = []
                current_size = 0

            current_messages.append(msg)
            current_size += msg_size + 1

        # Don't forget the last chunk
        if current_messages:
            chunk = self.create_chunk(current_messages, channel_name)
            if chunk:
                chunks.append(chunk)

        return chunks

    def process_channel(self, channel_dir: Path) -> List[Dict[str, Any]]:
        """Process a single channel directory."""
        channel_name = channel_dir.name
        chunks = []

        # Load all messages
        messages = self.load_messages_from_channel(channel_dir)
        self.stats['total_messages'] += len(messages)

        # Filter messages
        messages = self.filter_messages(messages)

        if not messages:
            return chunks

        # Group threads
        threads, main_messages = self.group_threads(messages)

        # Process threads
        for thread_ts, thread_messages in threads.items():
            thread_chunks = self.chunk_thread(thread_messages, channel_name, thread_ts)
            chunks.extend(thread_chunks)
            self.stats['threads_processed'] += 1

        # Process main messages
        main_chunks = self.chunk_main_messages(main_messages, channel_name)
        chunks.extend(main_chunks)

        self.stats['channels_processed'] += 1
        self.stats['total_chunks'] += len(chunks)

        print(f"  {channel_name}: {len(messages)} messages -> {len(chunks)} chunks")

        return chunks

    def process_all(self) -> Dict[str, Any]:
        """Process all channel directories."""
        all_chunks = []

        # Find all channel directories
        channel_dirs = [d for d in self.raw_dir.iterdir()
                       if d.is_dir() and not d.name.startswith('.')]

        print(f"Processing {len(channel_dirs)} channels...")

        for channel_dir in sorted(channel_dirs):
            chunks = self.process_channel(channel_dir)
            all_chunks.extend(chunks)

        return self._create_output(all_chunks)

    def _create_output(self, chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create the output dictionary."""
        return {
            'memories': chunks,
            'metadata': {
                'source': 'slack',
                'total_memories': len(chunks),
                'total_messages': self.stats['total_messages'],
                'channels_processed': self.stats['channels_processed'],
                'threads_processed': self.stats['threads_processed'],
                'chunking_params': {
                    'time_gap_threshold_hours': 1,
                    'min_chunk_size_chars': self.MIN_CHUNK_SIZE,
                    'max_chunk_size_chars': self.MAX_CHUNK_SIZE,
                }
            }
        }

    def save_output(self, data: Dict[str, Any], filename: str = 'slack_memories.json') -> Path:
        """Save the output to a JSON file."""
        output_path = self.output_dir / filename

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"Saved {len(data['memories'])} memories to {output_path}")
        return output_path


def main():
    """Main entry point."""
    import sys

    # Get script directory
    script_dir = Path(__file__).parent.parent

    if len(sys.argv) >= 3:
        raw_dir = sys.argv[1]
        output_dir = sys.argv[2]
    else:
        raw_dir = script_dir / 'raw' / 'slack'
        output_dir = script_dir / 'processed'

    if not Path(raw_dir).exists():
        print(f"Error: Input directory not found: {raw_dir}")
        print("Please run anonymize_slack.py first to generate anonymized data.")
        sys.exit(1)

    parser = SlackParser(str(raw_dir), str(output_dir))
    result = parser.process_all()
    parser.save_output(result)

    # Print summary
    print(f"\nSummary:")
    print(f"  Channels processed: {result['metadata']['channels_processed']}")
    print(f"  Threads processed: {result['metadata']['threads_processed']}")
    print(f"  Total messages: {result['metadata']['total_messages']}")
    print(f"  Total memories: {result['metadata']['total_memories']}")


if __name__ == '__main__':
    main()
