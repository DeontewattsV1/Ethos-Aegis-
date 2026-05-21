.PHONY: install demo docs verify test repl upgrade upgrade-dry clean help

help:
	@echo "Living Docs Template — canonical entry points"
	@echo ""
	@echo "  make install   # npm install"
	@echo "  make demo      # run a single representative example"
	@echo "  make docs      # regenerate README snippets + output snapshots"
	@echo "  make verify    # run all examples and diff against snapshots"
	@echo "  make test      # vitest with coverage"
	@echo "  make repl      # interactive REPL with .dot commands (.help inside)"
	@echo "  make upgrade   # bump deps within semver + regen docs + run tests + lint"
	@echo "  make upgrade-dry # list outdated deps without changing anything"
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

upgrade:
	npx tsx scripts/upgrade.ts

upgrade-dry:
	npx tsx scripts/upgrade.ts --dry-run

clean:
	rm -rf node_modules coverage docs/api
