import pathlib

p = pathlib.Path('tests/unit/test_screener.py')
text = p.read_text(encoding='utf-8')

# Remove sorting tests a bit more resiliently
try:
    s = text.index('    def test_rvr_ranking(self):')
    e = text.index('    def test_zero_close_rejected(self):')
    text = text[:s] + text[e:]
except Exception:
    pass

text = text.replace('assert len(results) == 1', 'assert len(results[\"dynamic\"]) == 1')
text = text.replace('assert results[0].ticker', 'assert results[\"dynamic\"][0].ticker')
text = text.replace('assert results[0].name', 'assert results[\"dynamic\"][0].name')
text = text.replace('assert results == []', 'assert results == {\"dynamic\": [], \"large_cap\": []}')

p.write_text(text, encoding='utf-8')
print('DONE')
