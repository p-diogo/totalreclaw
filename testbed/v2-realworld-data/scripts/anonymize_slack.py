#!/usr/bin/env python3
"""
Slack Data Anonymizer
Anonymizes Slack export data by replacing user IDs, names, emails, and channel names.
Preserves message structure and timestamps.

Usage:
    python anonymize_slack.py <source_dir> <output_dir>

Example:
    python anonymize_slack.py "/path/to/Slack export/" "./raw/slack/"
"""

import os
import re
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
from collections import defaultdict


class SlackAnonymizer:
    """Anonymizes Slack export data for privacy-preserving benchmarking."""

    # Patterns for PII detection
    EMAIL_PATTERN = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
    USER_MENTION_PATTERN = re.compile(r'<@([A-Z0-9]+)>')
    USER_ID_PATTERN = re.compile(r'^U[A-Z0-9]+$')
    CHANNEL_MENTION_PATTERN = re.compile(r'<#([A-Z0-9]+)\|([^>]+)>')
    URL_PATTERN = re.compile(r'<(https?://[^|>]+)(?:\|([^>]+))?>')

    def __init__(self, source_dir: str, output_dir: str):
        self.source_dir = Path(source_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Mappings
        self.user_id_map: Dict[str, str] = {}  # U01RB9A8XGS -> user_001
        self.user_name_map: Dict[str, str] = {}  # martin -> user_001 (same ID)
        self.channel_map: Dict[str, str] = {}  # channel name -> channel_001
        self.channel_id_map: Dict[str, str] = {}  # C01S1QYK4PJ -> channel_001

        # Reverse mappings for debugging
        self.user_id_reverse: Dict[str, str] = {}
        self.channel_reverse: Dict[str, str] = {}

        # Statistics
        self.stats = {
            'users_processed': 0,
            'channels_processed': 0,
            'messages_processed': 0,
            'files_processed': 0,
            'emails_removed': 0,
            'mentions_anonymized': 0,
        }

    def load_users(self) -> Dict[str, Any]:
        """Load and process users.json."""
        users_file = self.source_dir / 'users.json'
        if not users_file.exists():
            print(f"Warning: {users_file} not found")
            return {}

        with open(users_file, 'r', encoding='utf-8') as f:
            users = json.load(f)

        user_counter = 1
        for user in users:
            user_id = user.get('id')
            if not user_id:
                continue

            # Create anonymized ID
            anon_id = f"user_{user_counter:03d}"
            self.user_id_map[user_id] = anon_id
            self.user_id_reverse[anon_id] = user_id

            # Map username/real_name to same anonymized ID
            name = user.get('name', '')
            if name:
                self.user_name_map[name.lower()] = anon_id

            profile = user.get('profile', {})
            real_name = profile.get('real_name', '')
            if real_name:
                self.user_name_map[real_name.lower()] = anon_id

            display_name = profile.get('display_name', '')
            if display_name:
                self.user_name_map[display_name.lower()] = anon_id

            first_name = profile.get('first_name', '')
            if first_name:
                self.user_name_map[first_name.lower()] = anon_id

            user_counter += 1
            self.stats['users_processed'] += 1

        print(f"Processed {self.stats['users_processed']} users")
        return users

    def load_channels(self) -> Dict[str, Any]:
        """Load and process channels.json."""
        channels_file = self.source_dir / 'channels.json'
        if not channels_file.exists():
            print(f"Warning: {channels_file} not found")
            return {}

        with open(channels_file, 'r', encoding='utf-8') as f:
            channels = json.load(f)

        channel_counter = 1
        for channel in channels:
            channel_id = channel.get('id')
            channel_name = channel.get('name')

            if not channel_name:
                continue

            # Create anonymized channel name
            anon_name = f"channel_{channel_counter:03d}"
            self.channel_map[channel_name] = anon_name
            self.channel_reverse[anon_name] = channel_name

            if channel_id:
                self.channel_id_map[channel_id] = anon_name

            channel_counter += 1
            self.stats['channels_processed'] += 1

        print(f"Processed {self.stats['channels_processed']} channels")
        return channels

    def anonymize_text(self, text: str) -> str:
        """Anonymize PII in message text."""
        if not text:
            return text

        # Replace @mentions <@U01RB9A8XGS> -> <@user_001>
        def replace_user_mention(match):
            user_id = match.group(1)
            anon_id = self.user_id_map.get(user_id, f"unknown_user_{user_id}")
            self.stats['mentions_anonymized'] += 1
            return f"<@{anon_id}>"

        text = self.USER_MENTION_PATTERN.sub(replace_user_mention, text)

        # Replace channel mentions <#C01S1QYK4PJ|channel-name> -> <#channel_001>
        def replace_channel_mention(match):
            channel_id = match.group(1)
            anon_name = self.channel_id_map.get(channel_id, f"unknown_channel")
            return f"<#{anon_name}>"

        text = self.CHANNEL_MENTION_PATTERN.sub(replace_channel_mention, text)

        # Remove email addresses
        emails_found = self.EMAIL_PATTERN.findall(text)
        if emails_found:
            self.stats['emails_removed'] += len(emails_found)
            text = self.EMAIL_PATTERN.sub('[EMAIL_REMOVED]', text)

        # Clean up URLs - keep the link text but simplify the URL
        def replace_url(match):
            url = match.group(1)
            link_text = match.group(2) or url
            # Keep only the domain for context
            try:
                from urllib.parse import urlparse
                domain = urlparse(url).netloc
                return f"<{domain}|{link_text}>"
            except:
                return f"<URL_REMOVED>"

        text = self.URL_PATTERN.sub(replace_url, text)

        return text

    def anonymize_user_profile(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        """Strip PII from user_profile object, keeping only non-identifying fields."""
        if not profile:
            return {}

        # Keep only structural/non-PII fields
        safe_profile = {}

        # Keep boolean flags
        for key in ['is_restricted', 'is_ultra_restricted', 'is_bot', 'is_app_user']:
            if key in profile:
                safe_profile[key] = profile[key]

        # Remove all name/email/avatar fields
        # This intentionally strips: first_name, last_name, real_name, display_name,
        # email, phone, avatar_hash, image_*, etc.

        return safe_profile

    def anonymize_message(self, message: Dict[str, Any], channel_name: str) -> Dict[str, Any]:
        """Anonymize a single message."""
        anon_message = {}

        # Copy non-PII fields
        safe_fields = [
            'type', 'ts', 'thread_ts', 'parent_user_id', 'reply_count',
            'reply_users_count', 'latest_reply', 'subtype', 'hidden',
            'is_locked', 'client_msg_id', 'blocks', 'attachments',
            'reactions', 'files', 'edited', 'unfurl_links', 'unfurl_domain'
        ]

        for field in safe_fields:
            if field in message:
                anon_message[field] = message[field]

        # Anonymize user ID
        if 'user' in message:
            user_id = message['user']
            anon_message['user'] = self.user_id_map.get(user_id, f"unknown_user_{user_id}")

        # Anonymize parent_user_id if present
        if 'parent_user_id' in message:
            user_id = message['parent_user_id']
            anon_message['parent_user_id'] = self.user_id_map.get(user_id, f"unknown_user_{user_id}")

        # Anonymize text content
        if 'text' in message:
            anon_message['text'] = self.anonymize_text(message['text'])

        # Anonymize user_profile
        if 'user_profile' in message:
            anon_message['user_profile'] = self.anonymize_user_profile(message['user_profile'])

        # Anonymize reply_users list
        if 'reply_users' in message:
            anon_message['reply_users'] = [
                self.user_id_map.get(uid, f"unknown_user_{uid}")
                for uid in message['reply_users']
            ]

        # Anonymize replies list
        if 'replies' in message:
            anon_message['replies'] = [
                {'user': self.user_id_map.get(r['user'], f"unknown_user_{r['user']}"), 'ts': r['ts']}
                for r in message['replies']
            ]

        # Anonymize reactions
        if 'reactions' in message:
            anon_message['reactions'] = []
            for reaction in message['reactions']:
                anon_reaction = {
                    'name': reaction.get('name'),
                    'count': reaction.get('count'),
                    'users': [
                        self.user_id_map.get(uid, f"unknown_user_{uid}")
                        for uid in reaction.get('users', [])
                    ]
                }
                anon_message['reactions'].append(anon_reaction)

        # Store the anonymized channel name
        anon_message['channel'] = self.channel_map.get(channel_name, channel_name)

        return anon_message

    def process_channel_directory(self, channel_dir: Path) -> List[Dict[str, Any]]:
        """Process all daily JSON files in a channel directory."""
        channel_name = channel_dir.name
        anon_channel_name = self.channel_map.get(channel_name, channel_name)

        all_messages = []

        # Process each daily JSON file
        json_files = sorted(channel_dir.glob('*.json'))

        for json_file in json_files:
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    messages = json.load(f)

                if not isinstance(messages, list):
                    continue

                anon_messages = []
                for msg in messages:
                    anon_msg = self.anonymize_message(msg, channel_name)
                    anon_messages.append(anon_msg)
                    self.stats['messages_processed'] += 1

                # Save anonymized file
                anon_file_dir = self.output_dir / anon_channel_name
                anon_file_dir.mkdir(parents=True, exist_ok=True)
                anon_file_path = anon_file_dir / json_file.name

                with open(anon_file_path, 'w', encoding='utf-8') as f:
                    json.dump(anon_messages, f, ensure_ascii=False, indent=2)

                all_messages.extend(anon_messages)
                self.stats['files_processed'] += 1

            except Exception as e:
                print(f"Error processing {json_file}: {e}")

        return all_messages

    def save_mappings(self):
        """Save all mappings to a file for reference."""
        mappings = {
            'users': {
                'id_map': self.user_id_map,
                'name_map': self.user_name_map,
                'reverse': self.user_id_reverse
            },
            'channels': {
                'name_map': self.channel_map,
                'id_map': self.channel_id_map,
                'reverse': self.channel_reverse
            },
            'statistics': self.stats,
            'generated_at': datetime.now().isoformat()
        }

        mappings_path = self.output_dir / 'mappings.json'
        with open(mappings_path, 'w', encoding='utf-8') as f:
            json.dump(mappings, f, ensure_ascii=False, indent=2)

        print(f"Saved mappings to {mappings_path}")

    def process_all(self) -> Dict[str, Any]:
        """Process the entire Slack export."""
        print(f"Processing Slack export from: {self.source_dir}")
        print(f"Output directory: {self.output_dir}")

        # Load users and channels first
        users = self.load_users()
        channels = self.load_channels()

        # Save anonymized users.json (without PII)
        anon_users = []
        for user in users:
            user_id = user.get('id')
            anon_user = {
                'id': self.user_id_map.get(user_id, user_id),
                'deleted': user.get('deleted', False),
                'is_bot': user.get('is_bot', False),
                'is_app_user': user.get('is_app_user', False),
            }
            anon_users.append(anon_user)

        with open(self.output_dir / 'users.json', 'w', encoding='utf-8') as f:
            json.dump(anon_users, f, ensure_ascii=False, indent=2)

        # Save anonymized channels.json (without member lists)
        anon_channels = []
        for channel in channels:
            channel_name = channel.get('name')
            anon_channel = {
                'id': self.channel_id_map.get(channel.get('id'), channel.get('id')),
                'name': self.channel_map.get(channel_name, channel_name),
                'is_archived': channel.get('is_archived', False),
                'is_general': channel.get('is_general', False),
                'created': channel.get('created'),
            }
            anon_channels.append(anon_channel)

        with open(self.output_dir / 'channels.json', 'w', encoding='utf-8') as f:
            json.dump(anon_channels, f, ensure_ascii=False, indent=2)

        # Process all channel directories
        channel_dirs = [d for d in self.source_dir.iterdir() if d.is_dir() and not d.name.startswith('.')]

        total_channel_messages = {}
        for channel_dir in sorted(channel_dirs):
            messages = self.process_channel_directory(channel_dir)
            channel_name = channel_dir.name
            anon_channel_name = self.channel_map.get(channel_name, channel_name)
            total_channel_messages[anon_channel_name] = len(messages)
            print(f"  {channel_name} -> {anon_channel_name}: {len(messages)} messages")

        # Save mappings
        self.save_mappings()

        # Print summary
        print(f"\n=== Anonymization Summary ===")
        print(f"Users processed: {self.stats['users_processed']}")
        print(f"Channels processed: {self.stats['channels_processed']}")
        print(f"Messages processed: {self.stats['messages_processed']}")
        print(f"Files processed: {self.stats['files_processed']}")
        print(f"Emails removed: {self.stats['emails_removed']}")
        print(f"Mentions anonymized: {self.stats['mentions_anonymized']}")

        return {
            'statistics': self.stats,
            'channel_message_counts': total_channel_messages
        }


def main():
    """Main entry point."""
    import sys

    if len(sys.argv) >= 3:
        source_dir = sys.argv[1]
        output_dir = sys.argv[2]
    else:
        # Default paths
        source_dir = Path.home() / "Downloads" / "The Graph Foundation Slack export Jan 1 2025 - Feb 19 2026"
        script_dir = Path(__file__).parent.parent
        output_dir = script_dir / 'raw' / 'slack'

    if not Path(source_dir).exists():
        print(f"Error: Source directory not found: {source_dir}")
        sys.exit(1)

    anonymizer = SlackAnonymizer(str(source_dir), str(output_dir))
    result = anonymizer.process_all()


if __name__ == '__main__':
    main()
