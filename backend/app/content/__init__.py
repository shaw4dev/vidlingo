"""Content domain: the LessonPackage build artifact and its validator.

A LessonPackage is the compiled, immutable, versioned output of the content
pipeline (architecture.md §3, §6). The app renders a package directly, so the
schema here is the contract between the pipeline and the client.
"""
