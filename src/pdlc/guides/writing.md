# Write the prose a human will read

Use this guide for published prose: the record's authored sections, delivery task bodies, technical plans, verification reports, completion evidence, pull request bodies, commit messages, and review replies. A person reads each of these and acts on it, so the prose is part of the deliverable rather than a wrapper around it.

This guide does not govern code identifiers, log and error strings, test names, or product UI copy. It does not govern the record's structured fields either: an id, a gate state, a `file:line` pointer, or a verdict keeps the shape its format defines.

Within that scope the guide covers sentences and words. The record's sections decide structure, and each stage's brief decides content.

## Start with the sentence that says nothing

If a sentence could appear unchanged in another project's record, it says nothing about this one. Cut it.

Name the mechanism, the symbol, or the number instead. "Schema changes can cause issues" tells the reader nothing. "Renaming a column fails the build" tells them what happens.

## Say what it does, not how it feels

- Write the real symbol, path, flag, or command name, never a synonym for it or a description of it.
- Replace a claim about quality with the observable fact behind it. "Robust error handling" becomes the error the code returns, and where it returns it.
- Give the number wherever a number exists.
- If you cannot restate a sentence as a fact, an instruction, or a number, cut it.

## Sentences

- One thought per sentence. One instruction per sentence.
- Name the actor. "The loader parses the file", not "the file is parsed".
- Put the condition before the instruction: "To skip the UI stage, run `pdlc post skip`."
- Split any sentence the reader has to read twice.
- Vary length on purpose. A short sentence lands a point, and a longer one carries a fact together with its condition or consequence.
- Keep "only" next to the word it changes. "Only fails on growth" and "fails only on growth" say different things.
- Make every "it", "this", and "they" point at one obvious noun. Repeat the noun when in doubt.
- Break up noun stacks. "The proto import budget check script" becomes "the script that checks the proto-import budget".

## Words

- Use the short everyday word. "Use", not "utilize". "Help", not "facilitate". A long word has to buy its length with precision.
- Cut filler. "In order to" is "to". "It is important to note that" is nothing.
- Cut hedging. State what is true, or state what you could not determine and why.
- Cut an adverb propping up a weak verb. "Significantly improves" becomes the measured delta.
- Avoid abstract metaphor nouns: substrate, wedge, vector, locus, surface, scaffolding, north star, flywheel, endgame, ratchet. Say "base", "add", "way", "limit". Use the words a developer says out loud.
- No invented jargon, no aphorisms, no personified code. "The plan holds it" names nothing.
- Call one thing by one name everywhere in the record. A record that says "the gate", "the check", and "the guard" for one thing teaches three things.

## Formatting

- Headings are sentence case and carry the point, not just the topic.
- Numbered lists for sequences, bullets for everything else. Keep the items parallel.
- Code, paths, symbols, and commands go in backticks.
- Drop a bold label that restates the line it introduces. "**Performance:** Performance improved" is noise. A bold lead-in that names an item and is followed by new detail is fine.
- No decorative emoji.

## Terse fields stay terse

A structured field is not prose. Keep an identifier, a `file:line`, a verdict, or a one-line finding exactly as short as the format defines it. These rules govern the sentences around those fields, not the fields themselves. Never expand a template into paragraphs.

The opposite failure costs the reader just as much. Do not compress prose into symbol-speak: "Parser rejects bad date → exit 2, no write" becomes "The parser rejects a bad date, exits with code 2, and writes nothing."

## Review checklist

Apply this to any artifact you review, alongside the stage's own criteria.

1. Does every sentence say something true of this project, at this commit?
2. Is every symbol, path, count, and command real?
3. Does any sentence carry two thoughts or two instructions? Split it.
4. Can any word be cut without losing meaning? Cut it.
5. Does each thing have one name across the whole record?
6. Does every "it" and "this" point at one obvious noun?
7. Would a developer say these words out loud?
8. Is every claim of quality, safety, or completeness backed by the fact that shows it?
