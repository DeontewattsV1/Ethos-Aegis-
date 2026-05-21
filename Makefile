.PHONY: install demo docs verify test repl clean help

help:
	@echo "Living Docs Template — canonical entry points"
	@echo ""
	@echo "  make install   # npm install"
	@echo "  make demo      # run a single representative example"
	@echo "  make docs      # regenerate README snippets + output snapshots"
	@echo "  make verify    # run all examples and diff against snapshots"
	@echo "  make test      # vitest with coverage"
	@echo "  make repl      # interactive REPL with library preloaded"
	@echo "  make clean     # remove node_modules, coverage, generated docs/api"

install:
	npm install

demo:
	npx tsx examples/basic/01-subscribe.ts

docs:
	npx tsx scripts/sync-readme.ts
	npx tsx scripts/run-examples.ts
	npx tsx scripts/sync-readme.ts

verify:
	npx tsx scripts/run-examples.ts
	npx tsx scripts/validate-docs.ts

test:
	npx vitest run --coverage

repl:
	npx tsx repl.ts

clean:
	rm -rf node_modules coverage docs/api
