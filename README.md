# API-Spec-Pruner

A tool to extract and create a streamlined API specification by selecting necessary paths from a full API spec.
Only OpenAPI 3.x is supported. Please convert your Swagger 2.x to 3.0 before utilizing this tool.

## Features

- Extracts specific paths from a full API specification.
- Generates a simplified API spec for easier management and usage.

## Installation

To install the API-Spec-Pruner, clone the repository and navigate to the project directory:

```bash
git clone <repository-url>
cd API-Spec-Pruner
```

## Usage

Run the script to prune an API specification:
Replace <spec_filename> with the path to your full API spec and <required_paths> with the list of paths to extract for the pruned spec.

```bash
python shorten_api_spec.py
```


## Dependencies

- Python 3.x
- PyYAML (for YAML file handling)

Install the dependencies using pip:

```bash
pip install pyyaml
```
