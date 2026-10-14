.PHONY: run test

# Le projet vit dans track_2b/ : make run depuis la racine y est transmis.
run:
	$(MAKE) -C track_2b run

test:
	$(MAKE) -C track_2b test
