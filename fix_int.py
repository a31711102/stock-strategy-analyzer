import pathlib

p = pathlib.Path('tests/integration/test_batch_processing.py')
text = p.read_text(encoding='utf-8')

text = text.replace(
    'code, result, approaching = processor.process_single_stock',
    'code, result, approaching, atr_info = processor.process_single_stock'
)

p.write_text(text, encoding='utf-8')
print('DONE')
