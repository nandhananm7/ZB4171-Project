#!/usr/bin/env python3
"""List models available to YOUR SoCLaaS API key; optionally ping one chat model."""
import argparse
import os
from soclaas_client import get_client


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ping', metavar='MODEL_ID', help='Send a one-turn chat request to this model')
    args = parser.parse_args()
    client = get_client()
    print('Model IDs visible to your SoCLaaS key:')
    entries = sorted(m.id for m in client.models.list().data)
    for model_id in entries:
        print('  ' + model_id)
    if args.ping:
        print(f'\nTesting chat completion on model {args.ping!r} ...')
        response = client.chat.completions.create(
            model=args.ping,
            messages=[{'role': 'user', 'content': 'Reply with exactly OK.'}],
        )
        content = response.choices[0].message.content
        print('Response:', content)

if __name__ == '__main__':
    main()
