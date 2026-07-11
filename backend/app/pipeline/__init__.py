"""Content pipeline (T07): youtube_id -> LessonPackage -> DB.

Stages (architecture.md §6, ADR-001):
    captions.fetch -> captions.segment -> nlp.translate -> nlp.tokenize
    -> pipeline.build_lesson_package -> validate (T02) -> load_package (T03)

Pure logic (segmentation, tokenization, packaging) is dependency-free and tested
offline; the network/LLM stages (caption fetch, translation) are swappable
providers so they can be faked in tests and upgraded independently.
"""
