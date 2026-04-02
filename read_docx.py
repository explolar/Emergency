import zipfile
import xml.etree.ElementTree as ET

try:
    with zipfile.ZipFile(r"d:\Internship\hand\c\Project_details (1).docx") as document:
        xml_content = document.read('word/document.xml')
    tree = ET.XML(xml_content)
    WORD_NAMESPACE = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
    PARA = WORD_NAMESPACE + 'p'
    TEXT = WORD_NAMESPACE + 't'
    
    with open(r"d:\Internship\hand\c\output.txt", "w", encoding="utf-8") as f:
        for paragraph in tree.iter(PARA):
            texts = [node.text for node in paragraph.iter(TEXT) if node.text]
            if texts:
                f.write(''.join(texts) + '\n\n')
    print("Done writing to output.txt")
except Exception as e:
    import traceback
    traceback.print_exc()
