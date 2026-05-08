# Safety & Contributing

## Safety Notes

CoView controls real desktop input. Start with low-risk tasks, keep sensitive apps closed during testing, and watch the first few runs.

On macOS, grant only the permissions you understand:

- Accessibility
- Screen Recording
- Microphone

On Windows, avoid running the assistant as administrator unless you specifically need to control administrator-level windows.

Do not commit:

- Real API keys.
- Local runtime config containing secrets.
- Private screenshots or recordings.
- Local generated artifacts that are not intended for release.

## Contributing

Good first areas:

- Windows and macOS regression testing.
- Model adapter improvements.
- Safer task interruption and recovery.
- More examples and bilingual documentation.
- Packaging, signing, and release automation.

Please keep changes focused, add tests for behavior changes, and document user-facing behavior.

