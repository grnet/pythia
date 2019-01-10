# Pythia

This is a static analysis tool for Django-based applications focused on security.
It uses tainted flow analysis in order to find vulnerable data paths in the applications' views
and its templates.

For more information about the motivation and the tool's design decisions, check [this](docs/DESIGN.md)

## Features
1. Ability to parse django templates in order to find XSS vulnerabilities
2. Also tracks data from views to the templates
3. Resolves URLs to views so that we have actionable information when conducting security assessments
4. Finds `Cross Site Request Forgery` issues

## Install
```
pip install django-pythia
```

## How to Use

1. Setup your application's environment so that you are able to run `python manage.py runserver`  
2. Install `pythia` as shown above
3. export `DJANGO_SETTINGS_MODULE` equal to your django's settings, e.g. `myproject.settings`
4. Under your project's root, run `"export PYTHONPATH=$PYTHONPATH:${PWD}"`
5. Run `pythia`

## Usage
```
usage: pythia [-h] [-i IGNORE_VARIABLES [IGNORE_VARIABLES ...]]
              [-f DANGEROUS_FILTERS [DANGEROUS_FILTERS ...]]
              [-dd DANGEROUS_DECORATORS [DANGEROUS_DECORATORS ...]] [-w] [-d]

optional arguments:
  -h, --help            show this help message and exit
  -i IGNORE_VARIABLES [IGNORE_VARIABLES ...], 
  	--ignore-variables IGNORE_VARIABLES [IGNORE_VARIABLES ...]
  -f DANGEROUS_FILTERS [DANGEROUS_FILTERS ...], 
  	--dangerous-filters DANGEROUS_FILTERS [DANGEROUS_FILTERS ...]
  -dd DANGEROUS_DECORATORS [DANGEROUS_DECORATORS ...], 
  	--dangerous-decorators DANGEROUS_DECORATORS [DANGEROUS_DECORATORS ...]
  -w, --enable-warnings
  -d, --debug
```
