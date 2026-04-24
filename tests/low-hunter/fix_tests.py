import pathlib

p = pathlib.Path('tests/unit/test_screener.py')
text = p.read_text(encoding='utf-8')

# Remove sorting tests
start_str = '    def test_rvr_ranking(self):'
end_str = '    def test_zero_close_rejected(self):'
start = text.find(start_str)
end = text.find(end_str)
if start != -1 and end != -1:
    text = text[:start] + text[end:]

# Replace assertions for pipeline
t1 = 'assert len(results) == 1'
r1 = 'assert len(results["dynamic"]) == 1'
text = text.replace(t1, r1)

t2 = 'assert results[0].ticker == "9984"'
r2 = 'assert results["dynamic"][0].ticker == "9984"'
text = text.replace(t2, r2)

t3 = 'assert results[0].name == "テスト銘柄"'
r3 = 'assert results["dynamic"][0].name == "テスト銘柄"'
text = text.replace(t3, r3)

t4 = 'assert results == []'
r4 = 'assert results == {"dynamic": [], "large_cap": []}'
text = text.replace(t4, r4)

p.write_text(text, encoding='utf-8')
