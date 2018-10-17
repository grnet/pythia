- We have to choose a way to run the tool:
1. Require a proper virtualenv installation

* You have to install all dependencies to test
* More difficult to automate (????), since we have to automate installing the app's dependencies
* You dont have to mock the tags and filters, or care about environments etc
* Probably more django-version dependant (we have to use the project's django version)
* We can use `get_template` loaders etc.

2. Build our own environment with only `pythia` as a dependency

* Mock tags and filters with a change to break things already(This is too much work)
* Move all templates to a custom directory since we dont have access to TEMPLATE_DIRS
* Minimal work required from user
* Custom tags cannot be properly parsed.

- Parse extending templates just once (keep a table of which templates need to be parsed)
- Maybe make this a manage.py command instead? Will solve various issues
