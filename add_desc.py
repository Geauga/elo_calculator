import os

files_to_update = {
    "CODE_OF_CONDUCT.md": "<!-- Description: This document outlines our community standards and expectations for behavior. -->",
    "CONTRIBUTING.md": "<!-- Description: This document provides guidelines and instructions for contributing to the project. -->",
    "SECURITY.md": "<!-- Description: This document details our security policies and how to report vulnerabilities safely. -->",
    "SUPPORT.md": "<!-- Description: This document explains how to get help and find support for the project. -->"
}

for root in [r"C:\Code\elo_calculator", r"C:\Code\ringout"]:
    for filename, desc in files_to_update.items():
        filepath = os.path.join(root, filename)
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            if "<!-- Description:" not in content:
                content = desc + "\n" + content
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(content)
