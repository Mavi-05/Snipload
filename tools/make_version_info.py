"""Erzeugt die Windows-Versionsinfo (Rechtsklick > Eigenschaften > Details) fuer die exe."""
import sys

version = sys.argv[1] if len(sys.argv) > 1 else "0.0.0"
nums = [int(x) for x in version.split(".") if x.isdigit()][:4]
nums += [0] * (4 - len(nums))
t = tuple(nums)
text = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={t}, prodvers={t}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040704B0', [
      StringStruct('FileDescription', 'Snipload'),
      StringStruct('ProductName', 'Snipload'),
      StringStruct('FileVersion', '{version}'),
      StringStruct('ProductVersion', '{version}'),
      StringStruct('OriginalFilename', 'Snipload.exe')])]),
    VarFileInfo([VarStruct('Translation', [1031, 1200])])
  ]
)
"""
with open("tools/version_info.txt", "w", encoding="utf-8") as f:
    f.write(text)
# Build-Nummer fuer das Selbst-Update in die App schreiben (UTF-8, nicht ueber PowerShell!)
with open("src/snipload/_build.py", "w", encoding="utf-8") as f:
    f.write(f'BUILD = "{version}"\n')
print("Versionsinfo:", version)
