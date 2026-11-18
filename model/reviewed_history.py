"""Verify individually transcribed, unusually formatted issuer rows against the pinned publication."""
from decimal import Decimal
from functools import lru_cache
import hashlib
import json
from pathlib import Path

from issuer_statements import compact

ROOT = Path(__file__).resolve().parents[1]
HISTORY = ROOT/'results/issuer-annual-2026-11-18/historical'


@lru_cache(maxsize=1)
def reviewed():
    return json.loads((HISTORY/'reviewed-rows.json').read_bytes())


def verified_review(meta, record, report):
    review = reviewed().get(meta['id'])
    if not review or (review['filing_code'], review['year'], review['pdf_sha256']) != (
            meta['code'], report.year, record['pdf_sha256']):
        return {}
    if review.get('page_image'):
        image = (HISTORY/review['page_image']).read_bytes()
        if hashlib.sha256(image).hexdigest() != review['image_sha256']:
            return {}
    elif not report.cover_ok:
        return {}
    pages = report.text.split('\f')
    facts, limited, rows = {}, {}, {}
    for field, row in review['fields'].items():
        for page, *passages in row.get('checks', []):
            if any(compact(s) not in compact(pages[page-1]) for s in passages):
                raise ValueError(f'Published text mismatch: {meta["id"]}, {field}, PDF page {page}')
        if not row.get('checks') and not review.get('page_image'):
            raise ValueError('Review needs a hash-bound page')
        inputs = list(map(Decimal, row['amounts']))
        operation = row.get('operation', 'reported')
        if operation == 'reported':
            value, = inputs
        elif operation == 'sum':
            value = sum(inputs)
        elif operation == 'ratio':
            value = inputs[0] / inputs[1]
        elif operation == 'margin':
            if inputs[0] == 0:
                limited[field] = {'reason': 'zero_operating_revenue'}
                value = None
            else:
                value = (inputs[0] - inputs[1]) / inputs[0]
        elif operation == 'average_equity_roe':
            average = (inputs[1] + inputs[2]) / 2
            value = inputs[0] / average if average else None
            if average <= 0:
                limited[field] = {'reason':'nonpositive_average_parent_equity' if average else 'zero_average_parent_equity'}
                if average:
                    limited[field]['signed_formula_value'] = str(value)
                value = None
        else:
            raise ValueError('Unknown financial calculation: ' + operation)
        if value is not None:
            facts[field] = str(value)
        rows[field] = {**row, **({'page_image':review['page_image'], 'image_sha256':review['image_sha256']}
                                if review.get('page_image') else {})}
    return {'facts':facts, 'non_comparable':limited, 'evidence':rows}
