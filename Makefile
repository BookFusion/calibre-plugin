.PHONY: debug dist

debug:
	calibre-customize -b .
	calibre-debug -g

dist:
	mkdir -p dist
	if [ -f dist/BookFusion.zip ]; then rm dist/BookFusion.zip; fi
	zip -r dist/BookFusion.zip . -x@.zipignore
