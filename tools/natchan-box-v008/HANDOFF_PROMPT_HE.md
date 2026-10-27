הנחיות למתחזק תהליך המחקר — שילוב נתחן v008 וקבלת הפורמטים המקוריים

המטרה היא לשלב ניתוח אוטומטי אחרי אריזת ראיות ההרצה, לפני יצירת הדוח המחקרי. מקור הגרסה הוא geraw/library-demo בענף natchan-box-v008, בתיקייה tools/natchan-box-v008, לצד הגרסאות הקודמות. הוראות המשיכה נמצאות ב-README.md של הגרסה. הצמד את הקומיט המדויק של הענף ואל תסתמך על שם הענף המשתנה. נדרש checkout מלא בגלל התלויות במנתחים קודמים. גרסת v007 בקומיט 5cd95f132aa11906d9e42705143f9706a866c403 והמסמך FREEZE_v007 נשארים קפואים; כל שילוב חדש יתועד במסלול ממוספר חדש. אל תחליף תוצאות קודמות כאילו נוצרו ב-v008.

השינוי המרכזי הוא שיפוט סמנטי אחד על בקשות ותשובות שמורות מכל כלי: Provengo, EvoMaster, Schemathesis ו-RESTler. המנוע המשותף אינו בוחר כלל לפי שם הכלי. המטא־נתונים של המוצר נמצאים ב-JSON שמותאם ל-hash החוזה. תוצאות הכלי המקורי, מדידות STORY_CHECK והשיפוט העצמאי מה-HTTP נשמרים בנפרד. בלי תעבורה שמורה המדד המשותף אינו זמין, ואינו אפס.

השינויים הנוספים הם חישוב CONTRIB ו-COPY מגופי HTTP מלאים, בדיקת תנאי ההתחלה גם בתרחיש שעבר, קורא תעבורת RESTler ו-HAR, חיבור שמרני ללוג השרת, ספירה נפרדת של research ו-roundtrip ושל ניסיונות חוזרים, פרופיל Mealie מוגבל, ומנגנון הקפאת קוד והגדרות לקראת הערכה עתידית. הסיבה היא הפערים במסמך NATCHAN_v007_GAPS_20261027.md: השוואה לא אחידה לכלים, הסתמכות על מדידות המפיק, ותוצאות עוברות בלי תנאי התחלה מוכח. פירוט התיקון והמגבלות נמצא ב-GAPS_RESOLUTION.md.

ההכנה: הרץ מה-checkout של הנתחן את הבדיקות. אין צורך בהתקנת חבילות Python נוספות או בהרצת שרת. יש 275 בדיקות, ובהן תוצאות תקינות לצד כשלים, אותה תעבורה עם ארבעה שמות כלי, מתאמי מודל ו-baseline, לוג עמום, ספירת 294 רשומות RT סינתטיות, ובדיקה מכוונת של exit 4. זו בדיקת רגרסיה, לא קבלה של ZIP ה-login המקורי.

```powershell
python -m unittest discover -s .\tools\natchan-box-v008\tests -q
if ($LASTEXITCODE -ne 0) { throw 'Analyzer regressions failed.' }
git rev-parse HEAD
```

הקלט הקיים: לחבילת מודל, קמפיין, login או סיפורים השתמש במתאם toolkit-v1. אין לשנות את הבתים של ה-ZIP המקורי כדי להתאימם לנתחן. צור לידו קובץ analysis-request.json. גרסת שרת אינה מושלמת מהשערה: בחבילות הסיפורים השמורות ציין unknown, וב-login המקורי ציין v2.6.0 כפי שנרשם ב-ENV. השדות בבקשה הם טענות שנבדקות מול הראיות, ואינם ראיה חסרה.

```json
{
  "schema_version": "natchan-request/1",
  "run": {"id": "run-001", "tool": "provengo", "product": "mealie", "product_version": "unknown"},
  "evidence": {"adapter": "toolkit-v1", "archive": "review_stories.zip"}
}
```

ההרצה: צור תיקיית פלט חדשה לכל קלט. שמור מיד את קוד היציאה. קרא את result.json כסמן סופי, ובדוק שהקוד שבו מתאים לקוד התהליך. שמור גם stdout ו-stderr. אין להריץ מחדש את ה-SUT כדי לבצע ניתוח של ראיות קיימות.

```powershell
$requestPath = 'C:\experiment\analysis-request.json'
$outputPath = 'C:\experiment\analysis-v008-001'
python .\tools\natchan-box-v008\natchan.py --request $requestPath --output $outputPath
$analysisExit = $LASTEXITCODE
if (-not (Test-Path -LiteralPath (Join-Path $outputPath 'result.json'))) {
    throw "Analyzer did not commit result.json; exit=$analysisExit"
}
$result = Get-Content -LiteralPath (Join-Path $outputPath 'result.json') -Raw | ConvertFrom-Json
if ($analysisExit -ne $result.exit_code) { throw 'Analyzer exit/result mismatch.' }
Write-Host "NATCHAN_EXIT $analysisExit STATUS $($result.status)"
```

הקודים: אפס פירושו שהעיבוד הושלם, עם COMPLETE או PARTIAL, ולא שאין באגים. קוד 2 הוא קלט/תצורה פסולים או סתירה מזוהה; קוד 3 הוא פורמט או מדיניות לא נתמכים; קוד 4 הוא תקלה פנימית. כשל מפיק וכשל נתחן הם שני משתנים נפרדים. חבילה שלא הורצה אינה הוכחה לאפס ממצאים.

הקלט מהכלים האחרים: שמור raw HTTP לפני שהמידע הולך לאיבוד. בחבילת baseline אפשר להוסיף לכל תיקיית ריצה http-evidence.json או traffic.har או traffic.jsonl, לצד run-meta.json, ולשמור את הדוחות המקוריים. אפשר גם לנתח קובץ/ZIP בנפרד במתאם http-traffic. לקובצי RESTler מסוג network.*.txt או network.*.log יש מתאם restler-network. קורא RESTler נבדק מול פורמט הלוג הרשמי ו-fixtures בלבד; עליך לבצע קבלה עם ריצה אמיתית לפני שימוש מחקרי. לוג console או fuzzing_summary אינו תחליף לתעבורה.

הנתונים הדרושים לכל החלפה הם method, path אמיתי, input, response, status, זהות actor אטומה שנרשמה, epoch של איפוס, ואם יש case_id ו-request_id ו-t_utc. שם הכלי, המוצר, גרסה נצפית ו-hash החוזה נרשמים במטא־נתונים של המפיק. אין לגזור זהות actor מטוקן שכבר הוסתר ואין להניח שכל בקשה בתיקייה היא של אותו משתמש. אין למזג צילומי מצב בין איפוסים, בדיקות משולבות או ניסיונות חוזרים. פורמט מדויק ודוגמאות נמצאים ב-HTTP_EVIDENCE.md ובתיקיית examples.

הבקשה הגולמית לדוגמה משתמשת באותם קובצי הגדרות של השיפוט הסמנטי, בלי שמות באגים או תוצאות צפויות. אם הגרסה נצפתה, ציין אותה גם במטא־נתוני התעבורה וגם בבקשה. אם לא נצפתה, השאר אותה חסרה בתעבורה וכתוב unknown בבקשה.

```json
{
  "schema_version": "natchan-request/1",
  "run": {"id": "restler-001", "tool": "restler", "product": "my-product", "product_version": "unknown"},
  "evidence": {"adapter": "restler-network", "observations": "network.testing.1.txt"},
  "configuration": {"traffic_metadata": "traffic-meta.json", "story_semantics": "story-semantics.json"}
}
```

ההגדרות למוצר: אפשר לספק story-semantics.json בתוך החבילה או דרך configuration.story_semantics בקובץ חיצוני, אך לא בשניהם. הפרופיל מותאם ל-hash החוזה המדויק. המחולל derive_story_semantics.py מספק את בסיס הישויות, ההפניות, התצוגות והפעולות מהחוזה ומה-IR; הרחבות contributions/copies/aggregates הן כרגע הגדרות מפורשות שיש לבדוק ולהקפיא, ולא נוצרות אוטומטית כולן. פרופיל Mealie נבנה מ-IR שמור ומקישורי שדות ונתיבים שנבדקו; בתים מקוריים של החוזה אינם זמינים במאגר הזה והפער מופיע בפלט. אין לתאר אותו כשחזור מלא של החוזה או ככיסוי מלא של כל עסקי המערכת.

החיבור ללוג השרת: העדף request_id שמור משני הצדדים. אם אין, התאמה לפי method/path/status/time מותרת רק בהפעלה מפורשת, בזמנים עם אזור זמן ובייחודיות בשני הכיוונים. טקסט רגיל דורש regex מוגדר עם קבוצות בשמות; אין הנחה ששורת שגיאה קרובה בזמן שייכת לבקשה. גם הודעה מותאמת נשארת הקשר שמדווח בשרת, ולא הוכחת שורש סיבה.

הקבלה הנדרשת אצלך: הרץ על ה-ZIP המקוריים של הסיפורים, המודל, הקמפיין, ה-login וה-baselines ששימשו בעבר. השווה ספירות מהראיות הגולמיות, לא מה-NOTE. ב-login חייבים להיבדק בנפרד research=1369, known-failure=14, roundtrip-check=294, research5xx=5. שמור פערים וקוד יציאה לכל קלט. ריצה על 29 תתי־חבילות Git כבר בוצעה כאן, אך אינה קבלה של כל החבילות המלאות. אל תדרוש אפס פערים כשקובץ לא נשמר במקור.

הציפיות לתוצאות השמורות: ב-Mealie v2 מופיעים שני אירועי CONTRIB ושני אירועי COPY מתוך HTTP. אלה ארבעה מופעים המתארים שתי משפחות התנהגות, לא בהכרח ארבעה באגים שונים. ב-Gitea v2 יש שישה יחסי הפניה שלא הוקמו ושישה שהוקמו, שמתקבצים לחמישה אירועי תנאי התחלה; אין לאשר label כגורם ל-500. ב-wger נשמרות חתימות W-F2 עד W-F5, וב-Vikunja חתימת V-F1. אלה בדיקות בדיעבד על ראיות ששימשו לפיתוח, ולא הוכחת גילוי עצמאי.

ההשוואה בין הכלים: בדוח השלם הצג עמודה אחת לתוצאות הכלי המקורי ועמודה נפרדת לשיפוט המשותף על HTTP. השתמש ב-common_product_behavior_candidates למדד הסמנטי המותנה, ב-test_precondition_failures לכשלים בהקמת הבדיקה, וב-producer_measurement_occurrences למדידות המפיק. ערך null במדד המשותף הוא חוסר ראיות ולא אפס ממצאים. אל תסכם תוויות ומופעים כאילו היו באגים עצמאיים. הסבר את התנאים שלא הושגו ואת הדפוסים שלא נתמכים.

השלמות במפיק דורשות גרסה חדשה: רשום גרסת שרת שנצפתה; הפק manifest לפני יצירת ה-ZIP; שמור גוף GET מלא שמוכיח שההפניה אכן קשורה לאחר setup; רשום run_id/attempt_id/step_id/check_id/exchange_id מפורשים לניסיונות חוזרים. שמור את כל בקשות הביקורת והתגובות שלהן, כולל תמונות מצב מלאות לאטומיות. אל תשכתב חבילות ישנות ואל תציג inventory שהנתחן הפיק כ-manifest מקורי של המפיק.

הבדיקה העתידית על מערכת שלא נראתה נשארת פתוחה. אל תקרא ראיות Tandoor או כיוונוני ממצאים שלה כחלק מקבלת הרגרסיה. לפני צפייה בראיות חדשות, הקפא בקומיט את הגדרות הסמנטיקה המותרות והפק evaluation-freeze.json. הוסף configuration.evaluation_freeze לבקשה. המנגנון דוחה שינוי קוד/כללים/פרופילים, אך אינו מוכיח בעצמו שהרישום היה מראש או שהראיות לא נצפו. כל תיקון לאחר צפייה ידווח כהמשך בדיעבד.

```powershell
python .\tools\natchan-box-v008\evaluation_freeze.py --semantic-profile C:\experiment\story-semantics.json --output C:\experiment\evaluation-freeze.json
```

המסירה המבוקשת: קומיט שילוב ממוספר וקומיט הנתחן, קובצי בקשות והגדרות עם hashes, קודי יציאה וספירות לכל חבילה מקורית, פערים, רשימת אירועים עם הפניות לראיות, ודוח השוואה שמפריד בין כלי מקורי, שיפוט HTTP ומדידות מפיק. שמור מקור פרטי והפעל את נוהל ההסתרה לפני שיתוף תוצרים שעלולים להכיל נתיבים או מידע מהקלט.
