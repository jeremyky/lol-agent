


## 2026/03/13

do not start by writing OCR, first

start by defining
1. exact output contract
2. parsing stages
3. what evidence each stage is allowed to produce
4. how uncertainty will representated + handled

this is the ensure OCR has heuristics and JSON defined



1. lock the output schema

need to define one cannonical output shape


2. define pipeline before the modules

parser will be a pipeline of narrow stages

- image load + validation
- layout detection
- region proposal
  - slot based regions
  - column based regions
- low level evidence extraction
  - ocr tokens
  - icon similarity
  - color/brightness features
  - placeholder potrait score
- mid level interpretation
  - line clustering
  - champion matching
  - keyword detection
  - role detection
- slot inference
  - assign evidence to one of 5 slots
- turn inference
- ban inference
- result assembly
- debug artifact generation

each stage should consume typed inputs and return typed outputs. avoid passing around giant mutable dicts until the very end.