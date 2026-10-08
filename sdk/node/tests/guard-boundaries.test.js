"use strict";
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { AegisClient } = require("../src/index.js");

test("guard denies non-condemned but uncleared and incomplete HTTP verdicts", async () => {
  for (const verdict of [{sanctified:false,condemned:false}, {condemned:false},
                         {sanctified:true,condemned:false,sanitized:true}]) {
    const client = new AegisClient();
    client.adjudicate = async () => verdict;
    let called = false;
    const result = await client.guard({message:"raw", llmFn:async () => { called=true; return "bad"; }});
    assert.equal(result.blocked, true);
    assert.equal(called, false);
  }
});

test("guard passes the actual purified payload", async () => {
  const client = new AegisClient();
  client.adjudicate = async () => ({sanctified:true,condemned:false,sanitized:true,purified_payload:"clean"});
  let received;
  const result = await client.guard({message:"raw",llmFn:async (text) => {received=text;return "ok";}});
  assert.equal(result.blocked, false);
  assert.equal(received, "clean");
});
