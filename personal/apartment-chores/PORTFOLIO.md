Runs a three-person apartment's chores unattended on GitHub Actions since September 22, 2026,
splitting the quarter's 57 assignments exactly 19 each, sending a weekly digest and privately
nudging anyone overdue. Claude Sonnet 5 reads the landlord's emails into proposed cleaner
visits through structured output, and plain code checks that the quoted sentence appears in the
email and that any named weekday matches the date. Nothing takes effect until a roommate
confirms it. All configuration lives in Airtable, and 437 tests run offline.

Python, Airtable API, Gmail SMTP/IMAP, Claude API, GitHub Actions.
