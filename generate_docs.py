from flask import render_template
import os
from datetime import datetime

# Path to the templates and output directory
TEMPLATE_DIR = os.path.join(os.getcwd(), 'templates')
OUTPUT_DIR = os.path.join(os.getcwd(), 'output')

# Ensure the output directory exists
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Function to generate HTML files from templates

def generate_html_from_templates(data):
    for template_name in os.listdir(TEMPLATE_DIR):
        if template_name.endswith('.html'):
            # Render template with data
            rendered = render_template(template_name, data=data)
            # Create a filename for the output
            output_filename = os.path.join(OUTPUT_DIR, f'{os.path.splitext(template_name)[0]}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.html')
            # Write the rendered HTML to a file
            with open(output_filename, 'w') as f:
                f.write(rendered)
            print(f'Generated: {output_filename}')  

# Example data - replace with ResultCache data as needed
example_data = {'key': 'value'}

generate_html_from_templates(example_data)
