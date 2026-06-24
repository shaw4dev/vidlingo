# VidLingo iOS App

SwiftUI app (architecture.md §4). Requires macOS + Xcode 15+ to build — this
directory is a placeholder until the Xcode project is generated on a Mac.

## Planned module layout (architecture.md §4.1)
```
VidLingo/
├── Feature/Reader      # player + subtitle + word-tap + follow-read (T06–T11)
├── Feature/Vocab       # vocab book (T12)
├── Feature/Browse      # theme × difficulty grid (T13)
├── Feature/Review      # spaced repetition (T20–T21)
├── Feature/Discover    # recommend + role-play (T25, T27)
├── Feature/Profile     # level, stats, settings
├── Core/ContentCache   # offline LessonPackage store (T14)
├── Core/SyncEngine     # offline event queue → backend (T05)
├── Core/Analytics      # structured event emitter (T05)
└── Core/Entitlement    # RESERVED: returns .free in MVP (T29)
```

## Bootstrapping (on macOS, future task)
1. Create an Xcode project named `VidLingo` (SwiftUI, iOS 16+) inside this directory.
2. Add the module groups above.
3. CI builds it via the `ios-build` job in `.github/workflows/ci.yml`.
