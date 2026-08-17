# Library System Bug Report

## Summary
This document captures the known issues in the library management system used for validation and testing.

## Confirmed bugs

### 1. Loan overflow
Users can borrow more than the allowed number of books. The system fails to enforce the per-user loan limit when the overflow bug is active.

### 2. Hold theft
A borrower can take a book that is currently on hold by another user. The hold validation is bypassed when the attack path is enabled.

## Impact
- Violates business rules for book lending.
- Allows unauthorized access to reserved books.
- Causes incorrect behavior under automated test scenarios and simulated attacks.

## Notes
The bug scenarios are represented in the system test suite and reference files under the project.
