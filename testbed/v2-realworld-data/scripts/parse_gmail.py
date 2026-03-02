#!/usr/bin/env python3
"""
Gmail MBOX Parser

Parses MBOX files exported from Google Takeout and converts them into memory chunks.
Groups emails into threads and creates conversational chunks.
"""

import mailbox
import email
import re
import json
from email.utils import parsedate_to_datetime, getaddresses
from email.header import decode_header
from datetime import datetime
from collections import defaultdict
from typing import List, Dict, Any, Optional
import html
import sys


def decode_header_value(header_value: str) -> str:
    """Decode email header value that may be encoded."""
    if not header_value:
        return ""

    decoded_parts = []
    for part, encoding in decode_header(header_value):
        if isinstance(part, bytes):
            if encoding:
                try:
                    decoded_parts.append(part.decode(encoding))
                except (LookupError, UnicodeDecodeError):
                    decoded_parts.append(part.decode('utf-8', errors='replace'))
            else:
                decoded_parts.append(part.decode('utf-8', errors='replace'))
        else:
            decoded_parts.append(str(part))
    return "".join(decoded_parts)


def strip_html(html_content: str) -> str:
    """Strip HTML tags and convert to plain text."""
    if not html_content:
        return ""

    # Simple HTML tag removal
    text = re.sub(r'<[^>]+>', ' ', html_content)
    # Decode HTML entities
    text = html.unescape(text)
    # Clean up whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def extract_email_body(message: email.message.Message) -> str:
    """Extract email body, preferring plain text over HTML."""
    body = ""

    if message.is_multipart():
        for part in message.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))

            # Skip attachments
            if "attachment" in content_disposition:
                continue

            if content_type == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    try:
                        body = payload.decode(part.get_content_charset() or 'utf-8', errors='replace')
                        return body
                    except:
                        body = str(payload)

            elif content_type == "text/html" and not body:
                payload = part.get_payload(decode=True)
                if payload:
                    try:
                        html_body = payload.decode(part.get_content_charset() or 'utf-8', errors='replace')
                        body = strip_html(html_body)
                    except:
                        body = str(payload)
    else:
        content_type = message.get_content_type()
        payload = message.get_payload(decode=True)
        if payload:
            try:
                if content_type == "text/html":
                    body = strip_html(payload.decode(message.get_content_charset() or 'utf-8', errors='replace'))
                else:
                    body = payload.decode(message.get_content_charset() or 'utf-8', errors='replace')
            except:
                body = str(payload)

    return body


def extract_attachments(message: email.message.Message) -> List[Dict[str, str]]:
    """Extract attachment information (filename and type only)."""
    attachments = []

    for part in message.walk():
        content_disposition = str(part.get("Content-Disposition", ""))

        if "attachment" in content_disposition:
            filename = part.get_filename()
            if filename:
                attachments.append({
                    "filename": decode_header_value(filename),
                    "content_type": part.get_content_type(),
                    "size": len(part.get_payload(decode=True) or b"")
                })

    return attachments


def normalize_subject(subject: str) -> str:
    """Normalize subject for threading (remove reply/forward prefixes)."""
    if not subject:
        return "(no subject)"

    # Remove common reply/forward prefixes
    normalized = re.sub(r'^(Re|Fw|Fwd|RE|FW|FWD):\s*', '', subject.strip())
    return normalized


def get_thread_id(message: email.message.Message) -> str:
    """Get thread ID from References header or normalize subject."""
    # First try References header (most reliable for threading)
    references = message.get('References', '')
    if references:
        # Use the first message ID in references as thread root
        refs = [r.strip() for r in references.split() if r.strip()]
        if refs:
            return refs[0]

    # Fall back to In-Reply-To
    in_reply_to = message.get('In-Reply-To', '')
    if in_reply_to:
        return in_reply_to.strip()

    # Last resort: use normalized subject
    subject = decode_header_value(message.get('Subject', ''))
    return f"subject:{normalize_subject(subject)}"


def parse_email_address(addr_str: str) -> Dict[str, str]:
    """Parse email address into name and email."""
    if not addr_str:
        return {"name": "", "email": ""}

    # Use email.utils.getaddresses for proper parsing
    addrs = getaddresses([addr_str])
    if addrs and addrs[0]:
        name, email_addr = addrs[0]
        return {
            "name": decode_header_value(name),
            "email": email_addr or ""
        }
    return {"name": "", "email": ""}


def parse_mbox(mbox_path: str) -> List[Dict[str, Any]]:
    """Parse MBOX file and return list of email dictionaries."""
    emails = []
    mbox = mailbox.mbox(mbox_path)

    for message in mbox:
        try:
            # Parse date
            date_str = message.get('Date', '')
            try:
                date_dt = parsedate_to_datetime(date_str)
                date_iso = date_dt.isoformat()
            except:
                date_iso = None

            # Parse addresses
            from_addr = parse_email_address(message.get('From', ''))

            to_addrs = []
            to_header = message.get('To', '')
            if to_header:
                for _, addr in getaddresses([to_header]):
                    if addr:
                        to_addrs.append({
                            "name": decode_header_value(_),
                            "email": addr
                        })

            cc_addrs = []
            cc_header = message.get('Cc', '')
            if cc_header:
                for _, addr in getaddresses([cc_header]):
                    if addr:
                        cc_addrs.append({
                            "name": decode_header_value(_),
                            "email": addr
                        })

            # Extract body
            body = extract_email_body(message)

            # Extract attachments
            attachments = extract_attachments(message)

            email_data = {
                "message_id": message.get('Message-ID', ''),
                "thread_id": get_thread_id(message),
                "from": from_addr,
                "to": to_addrs,
                "cc": cc_addrs,
                "subject": decode_header_value(message.get('Subject', '')),
                "date": date_iso,
                "body": body[:10000],  # Limit body size
                "attachments": attachments,
                "has_attachments": len(attachments) > 0
            }

            emails.append(email_data)

        except Exception as e:
            print(f"Warning: Failed to parse email: {e}", file=sys.stderr)
            continue

    return emails


def group_into_threads(emails: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Group emails into conversation threads."""
    threads = defaultdict(list)

    for email in emails:
        thread_id = email.get('thread_id', 'unknown')
        threads[thread_id].append(email)

    # Sort emails in each thread by date
    result = []
    for thread_id, thread_emails in threads.items():
        # Sort by date, None dates go last
        sorted_emails = sorted(
            thread_emails,
            key=lambda e: (e.get('date') is None, e.get('date') or '')
        )

        # Use subject from first email as thread subject
        thread_subject = sorted_emails[0].get('subject', '(no subject)')

        result.append({
            "thread_id": thread_id,
            "subject": thread_subject,
            "email_count": len(sorted_emails),
            "emails": sorted_emails
        })

    # Sort threads by most recent email
    result.sort(
        key=lambda t: (
            not any(e.get('date') for e in t['emails']),
            max((e.get('date') or '') for e in t['emails'])
        ),
        reverse=True
    )

    return result


def create_memory_chunks(threads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Create memory chunks from email threads."""
    chunks = []
    chunk_id = 0

    for thread in threads:
        thread_id = thread['thread_id']
        subject = thread['subject']
        emails = thread['emails']

        # Create a chunk for each thread
        participants = set()
        all_recipients = []

        for email in emails:
            from_email = email.get('from', {}).get('email', '')
            if from_email:
                participants.add(from_email)

            for to_addr in email.get('to', []):
                email_addr = to_addr.get('email', '')
                if email_addr:
                    participants.add(email_addr)
                    all_recipients.append(to_addr)

            for cc_addr in email.get('cc', []):
                email_addr = cc_addr.get('email', '')
                if email_addr:
                    participants.add(email_addr)

        # Build conversation text
        conversation_parts = []
        for email in emails:
            from_name = email.get('from', {}).get('name') or email.get('from', {}).get('email', 'Unknown')
            email_date = email.get('date', 'Unknown date')
            email_body = email.get('body', '')

            part = f"From: {from_name}\nDate: {email_date}\n\n{email_body}"
            conversation_parts.append(part)

        conversation_text = "\n" + "-"*50 + "\n".join(conversation_parts)

        # Get date range
        dates = [e.get('date') for e in emails if e.get('date')]
        date_range = {
            "start": min(dates) if dates else None,
            "end": max(dates) if dates else None
        }

        chunk = {
            "id": f"gmail_chunk_{chunk_id}",
            "source": "gmail",
            "thread_id": thread_id,
            "subject": subject,
            "participants": list(participants),
            "date_range": date_range,
            "email_count": len(emails),
            "conversation": conversation_text,
            "emails": [
                {
                    "message_id": e.get('message_id'),
                    "from": e.get('from'),
                    "to": e.get('to'),
                    "subject": e.get('subject'),
                    "date": e.get('date'),
                    "has_attachments": e.get('has_attachments', False),
                    "attachment_count": len(e.get('attachments', []))
                }
                for e in emails
            ],
            "metadata": {
                "total_emails": len(emails),
                "has_attachments": any(e.get('has_attachments') for e in emails),
                "attachment_files": [
                    att['filename']
                    for e in emails
                    for att in e.get('attachments', [])
                ]
            }
        }

        chunks.append(chunk)
        chunk_id += 1

    return chunks


def create_sample_mbox(output_path: str):
    """Create a sample MBOX file for testing."""
    import tempfile
    import os

    sample_emails = [
        """From: sender@example.com
To: recipient@example.com
Subject: Test Thread - Initial Message
Date: Mon, 01 Jan 2024 10:00:00 -0500
Message-ID: <msg1@example.com>
Content-Type: text/plain

This is the first email in a test thread.
It has some content that we can use to verify parsing.

Best regards,
Sender
""",
        """From: recipient@example.com
To: sender@example.com
Subject: Re: Test Thread - Initial Message
Date: Mon, 01 Jan 2024 11:30:00 -0500
Message-ID: <msg2@example.com>
In-Reply-To: <msg1@example.com>
References: <msg1@example.com>
Content-Type: text/plain

Thanks for your message. This is a reply to create a thread.

On Mon, 1 Jan 2024, sender@example.com wrote:
> This is the first email in a test thread.
> It has some content that we can use to verify parsing.

Best,
Recipient
""",
        """From: sender@example.com
To: recipient@example.com
Subject: Re: Test Thread - Initial Message
Date: Tue, 02 Jan 2024 09:15:00 -0500
Message-ID: <msg3@example.com>
In-Reply-To: <msg2@example.com>
References: <msg1@example.com> <msg2@example.com>
Content-Type: text/plain

Great, the threading is working!

Best,
Sender
""",
        """From: newsletter@example.com
To: subscriber@example.com
Subject: Weekly Newsletter - Issue 42
Date: Wed, 03 Jan 2024 08:00:00 -0500
Message-ID: <newsletter@example.com>
Content-Type: text/html

<html>
<body>
<h1>Weekly Newsletter</h1>
<p>This week's top stories:</p>
<ul>
<li>Story 1</li>
<li>Story 2</li>
</ul>
</body>
</html>
""",
        """From: colleague@example.com
To: me@example.com
Cc: boss@example.com
Subject: Project Update - Q1 Planning
Date: Thu, 04 Jan 2024 14:00:00 -0500
Message-ID: <project@example.com>
Content-Type: text/plain

Hi team,

Here's the update on our Q1 planning.

Key milestones:
- Complete design review
- Finalize budget
- Hire 2 new engineers

Let me know if you have questions.

Best,
Colleague
"""
    ]

    with open(output_path, 'w') as f:
        for email_text in sample_emails:
            f.write(f"From MAILER-DAEMON {datetime.now().strftime('%a %b %d %H:%M:%S %Y')}\n")
            f.write(email_text)
            f.write("\n")

    print(f"Created sample MBOX file at: {output_path}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Parse Gmail MBOX export')
    parser.add_argument('input', help='Path to MBOX file or "sample" to create sample')
    parser.add_argument('-o', '--output', default='gmail_memories.json',
                        help='Output JSON file path (default: gmail_memories.json)')
    parser.add_argument('--create-sample', metavar='PATH',
                        help='Create a sample MBOX file at PATH and exit')

    args = parser.parse_args()

    # Handle sample creation
    if args.create_sample:
        create_sample_mbox(args.create_sample)
        return

    if args.input.lower() == 'sample':
        # Create and use a temporary sample file
        sample_path = '/tmp/sample_gmail.mbox'
        create_sample_mbox(sample_path)
        args.input = sample_path

    # Parse MBOX
    print(f"Parsing MBOX file: {args.input}")
    emails = parse_mbox(args.input)
    print(f"Parsed {len(emails)} emails")

    # Group into threads
    threads = group_into_threads(emails)
    print(f"Grouped into {len(threads)} threads")

    # Create memory chunks
    chunks = create_memory_chunks(threads)
    print(f"Created {len(chunks)} memory chunks")

    # Write output
    with open(args.output, 'w') as f:
        json.dump(chunks, f, indent=2)

    print(f"Output written to: {args.output}")

    # Print summary
    print("\n=== Summary ===")
    print(f"Total emails: {len(emails)}")
    print(f"Total threads: {len(threads)}")
    print(f"Total chunks: {len(chunks)}")

    threads_with_attachments = sum(1 for t in threads if any(e.get('has_attachments') for e in t['emails']))
    print(f"Threads with attachments: {threads_with_attachments}")


if __name__ == '__main__':
    main()
