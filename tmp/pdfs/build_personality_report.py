from pathlib import Path
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from pypdf import PdfReader

out = Path('output/pdf/supplier_personality_fix_and_testing.pdf')
out.parent.mkdir(parents=True, exist_ok=True)
styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name='ReportTitle', fontName='Helvetica-Bold', fontSize=19, leading=23, spaceAfter=9))
styles.add(ParagraphStyle(name='Section', fontName='Helvetica-Bold', fontSize=11, leading=14, spaceBefore=10, spaceAfter=4))
styles.add(ParagraphStyle(name='BodyReport', fontName='Helvetica', fontSize=10, leading=13, spaceAfter=5))
styles.add(ParagraphStyle(name='CodeReport', fontName='Courier', fontSize=8.5, leading=11, spaceAfter=5))
story=[]
def p(text, style='BodyReport'):
    story.append(Paragraph(text, styles[style]))
p('Supplier personality fix and testing', 'ReportTitle')
p('What was wrong', 'Section')
p('The game could label a supplier as selfish, fair, or altruistic, but it did not tell the AI which personality to use. All three received the same instructions. This meant the selected personality did not guide the AI when it reviewed offers or chatted with the buyer. Personality only affected the basic rules used when AI was unavailable.')
p('What changed', 'Section')
p('The game now tells the AI which personality to use and what that means:')
p('<b>Selfish:</b> Protect the supplier\'s profit and be less willing to offer a better deal.<br/><b>Fair:</b> Balance the buyer\'s and supplier\'s interests.<br/><b>Altruistic:</b> Be more willing to help the buyer while still making a profit.')
p('These instructions apply when judging an offer and during chat. The selected personality stays the same throughout the game. If no personality is selected, the game uses fair.')
p('How to reproduce the original problem', 'Section')
p('Use the version from before the fix. Compare a selfish supplier and an altruistic supplier using the same offer and conversation. Have a developer inspect the instructions sent to the AI: neither includes the selected personality. After the fix, those instructions differ. Two suppliers giving the same answer once does not prove a bug; both may reasonably accept or reject the same offer.')
p('How to test the updated game', 'Section')
p('<b>1. Start the server.</b> Save a valid AI key in backend/.env. Open PowerShell in the project folder and run:')
p('cd backend<br/>&amp; ..\\.venv\\Scripts\\python.exe -m uvicorn app.main:app --reload', 'CodeReport')
p('<b>2. Start a selfish game.</b> Open http://127.0.0.1:8000/docs. Expand POST /game/start, click Try it out, replace the entire request box with the text below, then click Execute:')
p('{"rounds": 10, "personality": "selfish"}', 'CodeReport')
p('Copy the session_id from the result. This is the ID for your new game.')
p('<b>3. Make an offer.</b> Open POST /game/negotiate and enter the following. Replace YOUR_ID with the ID you copied, keeping the quotation marks:')
p('{"session_id": "YOUR_ID", "wholesale_price": 20,<br/> "buyback_price": 10, "length": 3, "contract_type": "buyback"}', 'CodeReport')
p('<b>4. Try negotiating.</b> If the offer is rejected, open POST /game/negotiate/chat and send:')
p('{"session_id": "YOUR_ID",<br/> "message": "Can you lower the price? What terms can you offer?"}', 'CodeReport')
p('<b>5. Compare personalities.</b> Repeat steps 2 to 4 with fair and altruistic. Use each new game ID with the same offer and message. Over several exchanges, look for the tendencies described above. If the server reports AI errors, it may be using basic rules instead, so this would not verify AI behavior.')
p('What has been checked', 'Section')
p('Five automated tests passed using simulated AI replies. They check that the correct personality instructions reach the AI services and that the basic rules still work. Starting a selfish game also succeeded. Differences in real AI replies still need to be checked. To rerun the tests, open another PowerShell window in the backend folder:')
p('&amp; ..\\.venv\\Scripts\\python.exe -m unittest discover -s tests -v', 'CodeReport')
p('<b>If you see "Unknown demand history: string":</b> replace the entire game-start request with the example in step 2. The word "string" is an example placeholder, not a valid history ID. This error is unrelated to personality.')
SimpleDocTemplate(str(out), pagesize=(612,792), rightMargin=43, leftMargin=43, topMargin=36, bottomMargin=34).build(story)
reader=PdfReader(str(out))
print(f'{out}: {len(reader.pages)} page(s)')
assert len(reader.pages)==1
