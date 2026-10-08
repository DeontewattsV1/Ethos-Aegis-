"use strict";
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { AegisClient, AegisError } = require("../src/index.js");

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

test("middleware rejects object, array, null and boolean payloads before adjudication", async () => {
  const client = new AegisClient();
  let adjudications = 0;
  client.adjudicate = async () => {
    adjudications++;
    return {sanctified: true, condemned: false};
  };
  const middleware = client.middleware();
  for (const value of [{raw: "unscanned"}, ["unscanned"], null, false, 123]) {
    let code;
    let nextCalled = false;
    let response;
    const res = {
      status(value) {
        code = value;
        return {json(body) { response = body; }};
      },
    };
    const req = {body: {message: value}};
    await middleware(req, res, () => { nextCalled = true; });
    assert.equal(code, 400);
    assert.match(response.error, /expected a string payload/);
    assert.equal(nextCalled, false);
    assert.equal(req.body.message, value);
  }
  assert.equal(adjudications, 0);
});

test("middleware turns a condemned AegisError into a blocked response", async () => {
  const client = new AegisClient({throwOnCondemned: true});
  const condemned = {sanctified: false, condemned: true, depth: "CONDEMNED"};
  client.adjudicate = async () => { throw new AegisError("blocked", condemned); };
  const req = {body: {message: "unsafe input"}};
  let code;
  let response;
  let nextCalled = false;
  await client.middleware()(req, {
    status(value) {
      code = value;
      return {json(body) { response = body; }};
    },
  }, () => { nextCalled = true; });
  assert.equal(code, 400);
  assert.equal(response.depth, "CONDEMNED");
  assert.equal(req.aegisVerdict, condemned);
  assert.equal(nextCalled, false);
});

test("middleware forwards unexpected infrastructure failures to the error handler", async () => {
  const client = new AegisClient();
  const failure = new Error("transport failure");
  client.adjudicate = async () => { throw failure; };
  let forwarded;
  await client.middleware()({body: {message: "test"}}, {},
    (error) => { forwarded = error; });
  assert.equal(forwarded, failure);
});
