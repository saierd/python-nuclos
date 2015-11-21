BUILD_DIRECTORY=release
DOCUMENTATION_DIRECTORY=documentation
PACKAGE_CONTENT=nuclos.py default.ini LICENSE $(DOC_FOLDER)
DATE=$(shell date +%Y-%m-%d)

all: documentation package

package:
	@echo "Packaging the zip file..."
	@zip -r $(BUILD_DIRECTORY)/python-nuclos-$(DATE).zip $(PACKAGE_CONTENT)
	@echo "Packaging the tar file..."
	@tar -czf $(BUILD_DIRECTORY)/python-nuclos-$(DATE).tar.gz $(PACKAGE_CONTENT)

test:
	python3 test/test.py

coverage:
	cd test && coverage3 run test.py && coverage3 html

documentation: docco-installed
	@echo "Building documentation..."
	@docco -o $(DOCUMENTATION_DIRECTORY) documentation.py.md
	@mv $(DOCUMENTATION_DIRECTORY)/documentation.py.html $(DOCUMENTATION_DIRECTORY)/index.html

docco-installed: ; @command -v docco >/dev/null 2>&1 || { echo >&2 "Need docco for building the documentation. Aborting."; exit 1; }

publish-documentation: documentation
	git checkout gh-pages
	cp $(DOCUMENTATION_DIRECTORY)/index.html index.html
	git add index.html
	git commit -m "Update the documentation"
	git push origin gh-pages
	git checkout master

clean:
	@echo "Cleaning up..."
	@rm -f *.zip
	@rm -f *.tar.gz
	@rm -rf $(DOCUMENTATION_DIRECTORY)
