"""
JavaScript Missing Import / Require Detector.

Detects common Node and NPM modules used without a preceding require() or import.
Adds appropriate const module = require('module'); declarations.
"""

from __future__ import annotations

import re

from core.detectors.base import Detector
from core.models import ErrorType, Fix, Issue


KNOWN_JS_MODULES: dict[str, str] = {
    "fs": "const fs = require('fs');",
    "path": "const path = require('path');",
    "crypto": "const crypto = require('crypto');",
    "os": "const os = require('os');",
    "http": "const http = require('http');",
    "https": "const https = require('https');",
    "events": "const events = require('events');",
    "util": "const util = require('util');",
    "child_process": "const child_process = require('child_process');",
    "express": "const express = require('express');",
    "axios": "const axios = require('axios');",
    "lodash": "const _ = require('lodash');",
}


class JsMissingImportDetector(Detector):
    name = "js_missing_import"

    def detect(self, code: str) -> list[Issue]:
        issues: list[Issue] = []
        lines = code.splitlines()

        # Check existing require / import statements
        declared_modules: set[str] = set()
        for line in lines:
            m_req = re.findall(r'(?:const|let|var)\s+(\w+)\s*=\s*require\([\'"](\w+)[\'"]\)', line)
            for var_name, mod_name in m_req:
                declared_modules.add(var_name)
                declared_modules.add(mod_name)
            m_imp = re.findall(r'import\s+(\w+)\s+from\s+[\'"](\w+)[\'"]', line)
            for var_name, mod_name in m_imp:
                declared_modules.add(var_name)
                declared_modules.add(mod_name)

        for line_idx, line in enumerate(lines, start=1):
            for mod_name, import_stmt in KNOWN_JS_MODULES.items():
                if mod_name in declared_modules:
                    continue
                # Match module usage e.g. fs.readFileSync, path.join, crypto.createHash
                pattern = rf'\b{mod_name}\.[a-zA-Z0-9_]+'
                if re.search(pattern, line):
                    issues.append(Issue(
                        error_type=ErrorType.MISSING_IMPORT,
                        line=line_idx,
                        message=f"`{mod_name}` is used but not imported or required.",
                        detail=import_stmt,
                        confidence=0.95,
                    ))
                    declared_modules.add(mod_name)

        return issues

    def fix(self, code: str, issues: list[Issue]) -> Fix:
        import_lines = sorted({issue.detail for issue in issues})
        fixed_code = "\n".join(import_lines) + "\n\n" + code.lstrip()

        names = ", ".join(sorted({i.message.split("`")[1] for i in issues}))
        explanation = f"Added missing JavaScript module require statement(s) for `{names}`: {'; '.join(import_lines)}."

        return Fix(
            fixed_code=fixed_code,
            explanation=explanation,
            issues_addressed=issues,
            source="local_engine_js",
        )
