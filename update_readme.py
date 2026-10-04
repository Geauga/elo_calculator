import os

with open("README.md", 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace("176 tests", "179 tests")
content = content.replace("40FFF3E941E2078A8816DA11809C0ACB478628828C47B64A70E8FD4BACBD3570", "FF54EF08495DC17FBC5B5F28E628E0FB307FF82C609757A01CEF64D60D7BA98C")
content = content.replace("A90F83CD309636871DA61A76B647D32246B615B54D0942E4AE721813379FB6E5", "472635E01E44C9C9DE0133A5F54F9D5762A2318E50636C465529EE612DA7C5A3")
content = content.replace("v28 executable", "v29 executable")
content = content.replace("163 tests passed", "179 tests passed")
content = content.replace("discovered 163 tests", "discovered 179 tests")
content = content.replace("schema 11", "schema 12")

with open("README.md", 'w', encoding='utf-8') as f:
    f.write(content)
