DOC_FOLDER = documentation
PACKAGE_CONTENT = nuclos.py default.ini LICENSE $(DOC_FOLDER)
DATE = $(shell date +%Y-%m-%d)

all: documentation package

package:
	@echo "Packaging the zip file..."
	@zip -r python-nuclos-$(DATE).zip $(PACKAGE_CONTENT)
	@echo "Packaging the tar file..."
	@tar -czf python-nuclos-$(DATE).tar.gz $(PACKAGE_CONTENT)

documentation: docco-installed
	@echo "Building documentation..."
	@docco -o $(DOC_FOLDER) documentation.py.md
	@mv $(DOC_FOLDER)/documentation.py.html $(DOC_FOLDER)/index.html

docco-installed: ; @command -v docco >/dev/null 2>&1 || { echo >&2 "Need docco for building the documentation. Aborting."; exit 1; }

clean:
	@echo "Cleaning up..."
	@rm -f *.zip
	@rm -f *.tar.gz
	@rm -rf $(DOC_FOLDER)
