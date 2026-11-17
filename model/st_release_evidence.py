"""Strict extraction of explicit, dated ST-to-normal name changes in issuer notices.

Only a date and name change in the same short passage qualify. Unsupported
formats remain unknown; title keywords or price-limit changes alone never pass.
"""
from datetime import date
import re


def extract(meta, text):
    try:
        effective=date.fromisoformat(meta['statDate'])
        published=date.fromisoformat(meta['available_date'])
        if not published<effective or (effective-published).days>30:return None
        title=meta['title'].replace('撤消','撤销')
        if '撤销' not in title or '风险警示' not in title:return None
        if any(word in title for word in ('申请','意见','核查','终止上市','退市整理')):return None
        text=re.sub(r'\s+','',text).replace('撤消','撤销')
        code=meta['code'].split('.')[-1]
        if not re.search(r'(?<!\d)'+code+r'(?!\d)',text[:500]):return None
        dates=[]
        for match in re.finditer(r'(20\d{2})年(\d{1,2})月(\d{1,2})日',text):
            try: observed=date(*map(int,match.groups()))
            except ValueError:continue  # unrelated PDF layout artifacts are not dates
            if observed!=effective:continue
            before=text[max(0,match.start()-45):match.start()]
            after=text[match.end():match.end()+45]
            if (re.search(r'撤销[^。；]{0,25}风险警示[^。；]{0,10}起始日(?:期)?[：:]?$',before)
                or re.match(r'[^。；]{0,22}撤销[^。；]{0,12}风险警示',after)):
                dates.append(match)
        for match in dates:
            passage=text[max(0,match.start()-150):match.end()+300]
            names=list(re.finditer(r'(?:股票|证券)简称[：:]?(?:将)?(?:由|从)[“\"]([^”\"]{1,30})[”\"](?:变更|更改|恢复)为[“\"]([^”\"]{1,30})[”\"]',passage))
            for name in names:
                old,new=name.groups()
                if 'ST' not in old.upper() or any(w in new.upper() for w in ('ST','退')):continue
                if not re.fullmatch(r'[\u4e00-\u9fffA-Za-z0-9、，,＆&·-]{2,30}',new):continue
                return {'effective_date':effective.isoformat(),'available_date':published.isoformat(),
                        'status':'normal_listing','old_name':old,'new_name':new,
                        'extraction_method':'explicit_date_and_ST_to_normal_name_in_same_passage_v1',
                        'excerpt':passage}
    except (ValueError,KeyError,TypeError):return None
    return None
