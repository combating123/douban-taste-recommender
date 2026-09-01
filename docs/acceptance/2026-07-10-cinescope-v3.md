# CineScope V3 鍥涜鍙ｈ瑙夐獙鏀?

- 鏃ユ湡锛?026-07-11锛堣鍒掓枃浠舵部鐢?2026-07-10 鍛藉悕锛?
- 鏈嶅姟锛歏3锛岀粦瀹?127.0.0.1:7862锛屾暟鎹洰褰?output/acceptance-data
- 鏈€缁堟祻瑙堝櫒婧愶細http://acceptance-20260711.localhost:7862锛堝悓涓€ 127/8 loopback 鏈嶅姟锛涚敤浜庣粫杩囨棫闈欐€佹ā鍧楃紦瀛橈級
- 璇佹嵁婧愶細output/acceptance/evidence.json
- 鏈€缁堢粨鏋滐細40 涓?route/viewport 缁勫悎锛?0 涓?audit 閫氳繃锛?0 寮犳渶缁堟埅鍥撅紱鍙︿繚鐣?10 寮?1440px 鐒︾偣鏍峰紡淇鍓嶆埅鍥俱€?

## 鍥哄畾楠屾敹浼氳瘽

- sessionId: 49c2e02bea0c4664baa6d122d89767ab
- titleId: douban:1291879
- personId: derived:6buR5rO95piO
- 璇ヤ細璇濈敱 window.__CINESCOPE_SEED_ACCEPTANCE__() 鍒涘缓涓€娆★紱鍥涗釜瑙嗗彛澶嶇敤鐩稿悓 ID銆?
- 鏍锋湰浼氳瘽褰撳墠娌℃湁鍙彃鍏?DOM 鐨?ready 鏈湴鍥剧墖锛屽洜姝ら〉闈娇鐢ㄨ璁″瀷 CSS fallback锛涙病鏈変互鎹熷潖鎴栧閾?img 闅愯棌缂哄彛銆傜湡瀹炲獟浣撹鐩栫巼鍦?Rollout Task 6 鐙珛璁板綍銆?

## 鍚姩涓庨噰闆?

~~~powershell
$env:CINESCOPE_UI_VERSION='v3'
$env:CINESCOPE_DATA_DIR="$PWD\output\acceptance-data"
$env:PYTHONPATH="$PWD\src"
python -m douban_recommender.web --host 127.0.0.1 --port 7862 --no-browser
~~~

姣忛〉绛夊緟 route commit銆乤ria-busy=0銆佸浘鐗囧畬鎴愪笌闈炵┖鍐呭锛屽啀杩愯鏈湴 audit helper 骞朵繚瀛?viewport PNG銆?90px 棰濆瑕佹眰 desktop rail 闅愯棌銆乥ottom nav 鍙銆乨ocument/body 鏃犳í鍚戞粴鍔ㄣ€?

## 鐪熷疄娴忚鍣ㄥ彂鐜颁笌 TDD 淇

1. **楠屾敹绉嶅瓙瀹夊叏 ID 璺敱**锛氱湡瀹炴湰鍦?HTTP fixture 璇佹槑瀹夊叏鐨?douban:... / derived:... ID 鑻ョ粡 encodeURIComponent 浼氫笌褰撳墠 API path contract 涓嶄竴鑷淬€備繚鐣?safeId锛堟嫆缁濇枩鏉犮€乹uery/hash銆?銆?.锛夊悗浣跨敤鍘熷瀹夊叏 segment锛涘彲鎵ц HTTP 娴嬭瘯鏂█ raw GET path銆?
2. **绋嬪簭鍖?route focus 閫犳垚宸ㄥぇ榛樿 outline 涓庡绔嬫柇琛?*锛?440px 鐨?Tonight銆乀itle銆丳erson 绛夐〉闈㈠嚭鐜版祻瑙堝櫒榛樿 focus ring 绌胯繃宸ㄥ瀷鏍囬锛孴onight 鏈熬浠?1鈥? 瀛楀绔嬫崲琛屻€備慨澶嶄负 route focus target 鏃犻粯璁よ瑙?outline銆佹爣棰?balance/姝ｅ父鏂瘝銆乀onight 瀛楀彿鍜屽搴﹂噸鏁淬€?200px 涓?intro 鏀逛负绾靛悜锛涘悓鏃跺帇绱?rail controls銆備慨澶嶅墠璇佹嵁浣嶄簬 output/acceptance/1440x900/*-before-focus-fix.png銆?
3. **390px 椤堕儴 288px 绌虹櫧**锛歮ax-width:960px 鐨?.shell-status { flex:1 1 18rem } 鍦?720px 绾靛悜 top bar 涓户缁敓鏁堬紝浣跨姸鎬佹爮楂樺害杈惧埌 288px銆傛柊澧炲け璐ユ祴璇曞悗锛屽湪 mobile rule 閲嶇疆涓?flex:0 1 auto锛涙渶缁堟墍鏈?390px 椤甸潰 top bar 绾?94.4px銆佺姸鎬佹爮绾?17.3px銆?

## 姹囨€昏仈绯昏〃

- output/acceptance/contact-sheets/1440x900.png
- output/acceptance/contact-sheets/1280x800.png
- output/acceptance/contact-sheets/1024x768.png
- output/acceptance/contact-sheets/390x844.png

## 閫愰〉璇佹嵁

| 瑙嗗彛 | Route | 鎴浘 | Audit / 甯冨眬璇佹嵁 | 瑙傚療涓庢渶缁堢姸鎬?|
|---|---|---|---|---|
| 1440x900 | /tonight | output/acceptance/1440x900/tonight.png | viewport=1440脳900; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 绋嬪簭鍖?focus/鏍囬鏂淇鍚庡楠岋紱PASS |
| 1440x900 | /tonight/movie | output/acceptance/1440x900/tonight-movie.png | viewport=1440脳900; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 绋嬪簭鍖?focus/鏍囬鏂淇鍚庡楠岋紱PASS |
| 1440x900 | /tonight/series | output/acceptance/1440x900/tonight-series.png | viewport=1440脳900; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 绋嬪簭鍖?focus/鏍囬鏂淇鍚庡楠岋紱PASS |
| 1440x900 | /tonight/anime-series | output/acceptance/1440x900/tonight-anime-series.png | viewport=1440脳900; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 绋嬪簭鍖?focus/鏍囬鏂淇鍚庡楠岋紱PASS |
| 1440x900 | /title/douban:1291879 | output/acceptance/1440x900/title-douban-1291879.png | viewport=1440脳900; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 绋嬪簭鍖?focus/鏍囬鏂淇鍚庡楠岋紱PASS |
| 1440x900 | /person/derived:6buR5rO95piO | output/acceptance/1440x900/person-derived-6buR5rO95piO.png | viewport=1440脳900; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 绋嬪簭鍖?focus/鏍囬鏂淇鍚庡楠岋紱PASS |
| 1440x900 | /universe | output/acceptance/1440x900/universe.png | viewport=1440脳900; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 绋嬪簭鍖?focus/鏍囬鏂淇鍚庡楠岋紱PASS |
| 1440x900 | /library | output/acceptance/1440x900/library.png | viewport=1440脳900; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 绋嬪簭鍖?focus/鏍囬鏂淇鍚庡楠岋紱PASS |
| 1440x900 | /taste | output/acceptance/1440x900/taste.png | viewport=1440脳900; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 绋嬪簭鍖?focus/鏍囬鏂淇鍚庡楠岋紱PASS |
| 1440x900 | /health | output/acceptance/1440x900/health.png | viewport=1440脳900; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 绋嬪簭鍖?focus/鏍囬鏂淇鍚庡楠岋紱PASS |
| 1280x800 | /tonight | output/acceptance/1280x800/tonight.png | viewport=1280脳800; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 鏈彂鐜版柊澧炶瑙夌己闄凤紱PASS |
| 1280x800 | /tonight/movie | output/acceptance/1280x800/tonight-movie.png | viewport=1280脳800; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 鏈彂鐜版柊澧炶瑙夌己闄凤紱PASS |
| 1280x800 | /tonight/series | output/acceptance/1280x800/tonight-series.png | viewport=1280脳800; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 鏈彂鐜版柊澧炶瑙夌己闄凤紱PASS |
| 1280x800 | /tonight/anime-series | output/acceptance/1280x800/tonight-anime-series.png | viewport=1280脳800; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 鏈彂鐜版柊澧炶瑙夌己闄凤紱PASS |
| 1280x800 | /title/douban:1291879 | output/acceptance/1280x800/title-douban-1291879.png | viewport=1280脳800; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 鏈彂鐜版柊澧炶瑙夌己闄凤紱PASS |
| 1280x800 | /person/derived:6buR5rO95piO | output/acceptance/1280x800/person-derived-6buR5rO95piO.png | viewport=1280脳800; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 鏈彂鐜版柊澧炶瑙夌己闄凤紱PASS |
| 1280x800 | /universe | output/acceptance/1280x800/universe.png | viewport=1280脳800; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 鏈彂鐜版柊澧炶瑙夌己闄凤紱PASS |
| 1280x800 | /library | output/acceptance/1280x800/library.png | viewport=1280脳800; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 鏈彂鐜版柊澧炶瑙夌己闄凤紱PASS |
| 1280x800 | /taste | output/acceptance/1280x800/taste.png | viewport=1280脳800; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 鏈彂鐜版柊澧炶瑙夌己闄凤紱PASS |
| 1280x800 | /health | output/acceptance/1280x800/health.png | viewport=1280脳800; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 鏈彂鐜版柊澧炶瑙夌己闄凤紱PASS |
| 1024x768 | /tonight | output/acceptance/1024x768/tonight.png | viewport=1024脳768; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 鏈彂鐜版柊澧炶瑙夌己闄凤紱PASS |
| 1024x768 | /tonight/movie | output/acceptance/1024x768/tonight-movie.png | viewport=1024脳768; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 鏈彂鐜版柊澧炶瑙夌己闄凤紱PASS |
| 1024x768 | /tonight/series | output/acceptance/1024x768/tonight-series.png | viewport=1024脳768; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 鏈彂鐜版柊澧炶瑙夌己闄凤紱PASS |
| 1024x768 | /tonight/anime-series | output/acceptance/1024x768/tonight-anime-series.png | viewport=1024脳768; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 鏈彂鐜版柊澧炶瑙夌己闄凤紱PASS |
| 1024x768 | /title/douban:1291879 | output/acceptance/1024x768/title-douban-1291879.png | viewport=1024脳768; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 鏈彂鐜版柊澧炶瑙夌己闄凤紱PASS |
| 1024x768 | /person/derived:6buR5rO95piO | output/acceptance/1024x768/person-derived-6buR5rO95piO.png | viewport=1024脳768; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 鏈彂鐜版柊澧炶瑙夌己闄凤紱PASS |
| 1024x768 | /universe | output/acceptance/1024x768/universe.png | viewport=1024脳768; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 鏈彂鐜版柊澧炶瑙夌己闄凤紱PASS |
| 1024x768 | /library | output/acceptance/1024x768/library.png | viewport=1024脳768; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 鏈彂鐜版柊澧炶瑙夌己闄凤紱PASS |
| 1024x768 | /taste | output/acceptance/1024x768/taste.png | viewport=1024脳768; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 鏈彂鐜版柊澧炶瑙夌己闄凤紱PASS |
| 1024x768 | /health | output/acceptance/1024x768/health.png | viewport=1024脳768; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=true; bottom=false | 鏈彂鐜版柊澧炶瑙夌己闄凤紱PASS |
| 390x844 | /tonight | output/acceptance/390x844/tonight.png | viewport=390脳844; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=false; bottom=true | 绉诲姩 top-bar flex-basis 淇鍚庡楠岋紱PASS |
| 390x844 | /tonight/movie | output/acceptance/390x844/tonight-movie.png | viewport=390脳844; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=false; bottom=true | 绉诲姩 top-bar flex-basis 淇鍚庡楠岋紱PASS |
| 390x844 | /tonight/series | output/acceptance/390x844/tonight-series.png | viewport=390脳844; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=false; bottom=true | 绉诲姩 top-bar flex-basis 淇鍚庡楠岋紱PASS |
| 390x844 | /tonight/anime-series | output/acceptance/390x844/tonight-anime-series.png | viewport=390脳844; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=false; bottom=true | 绉诲姩 top-bar flex-basis 淇鍚庡楠岋紱PASS |
| 390x844 | /title/douban:1291879 | output/acceptance/390x844/title-douban-1291879.png | viewport=390脳844; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=false; bottom=true | 绉诲姩 top-bar flex-basis 淇鍚庡楠岋紱PASS |
| 390x844 | /person/derived:6buR5rO95piO | output/acceptance/390x844/person-derived-6buR5rO95piO.png | viewport=390脳844; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=false; bottom=true | 绉诲姩 top-bar flex-basis 淇鍚庡楠岋紱PASS |
| 390x844 | /universe | output/acceptance/390x844/universe.png | viewport=390脳844; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=false; bottom=true | 绉诲姩 top-bar flex-basis 淇鍚庡楠岋紱PASS |
| 390x844 | /library | output/acceptance/390x844/library.png | viewport=390脳844; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=false; bottom=true | 绉诲姩 top-bar flex-basis 淇鍚庡楠岋紱PASS |
| 390x844 | /taste | output/acceptance/390x844/taste.png | viewport=390脳844; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=false; bottom=true | 绉诲姩 top-bar flex-basis 淇鍚庡楠岋紱PASS |
| 390x844 | /health | output/acceptance/390x844/health.png | viewport=390脳844; broken=0; external=0; overflow=0; focus=0; empty=false; hscroll=false; rail=false; bottom=true | 绉诲姩 top-bar flex-basis 淇鍚庡楠岋紱PASS |

## 闂ㄧ缁撹

- brokenImages=[]锛?0/40
- externalImages=[]锛?0/40
- overflowNodes=[]锛?0/40
- focusFailures=[]锛?0/40
- emptyMain=false锛?0/40
- 椤甸潰妯悜婊氬姩锛?/40
- 390px desktop rail 鍙锛?/10锛沚ottom nav 鍙锛?0/10
- Canary identity mismatch锛氭湰 Task 鏈瀵熷埌锛涙渶缁堝獟浣撹韩浠?瑕嗙洊闂ㄧ鐢?Task 6 缁撳悎 diagnostics 澶嶆牳銆?

## Rollout Task 5锛氱湡瀹炲悓姝ャ€佹帹鑽愩€佹崲鎵逛笌鍒锋柊楠屾敹

- 鏃ユ湡锛?026-07-12
- V3 涓撶敤鏈嶅姟锛歚127.0.0.1:7875`
- 鏁版嵁鐩綍锛歚output/task5-acceptance-data`
- 鏈€缁堟祻瑙堝櫒婧愶細`http://task5-fixed-20260712.localhost:7875`锛堟柊 loopback 瀛愬煙鐢ㄤ簬缁曡繃鏃?ES module 缂撳瓨锛?
- 鍚姩浠嶈姹傛樉寮忚缃?`CINESCOPE_UI_VERSION=v3`锛涙湭鏀瑰彉榛樿 legacy 鍥炴粴璺緞銆?

### 鍏紑璞嗙摚鍚屾

- 杈撳叆锛歚https://www.douban.com/people/<your-douban-id>/`
- job锛歚e4ce2171b3194fcd9ffe479cd5eeca3b`
- 鏈€缁堢姸鎬侊細`complete`锛沀I 鏄剧ず鈥滃悓姝ュ畬鎴愨€濄€?
- 瀹為檯瀹炴椂缁撴灉锛氭潯鐩?`280`锛岀湅杩?`244`锛屾兂鐪?`36`锛屾垚鍔熼〉 `22`锛屽け璐ラ〉 `0`銆?
- 鍘熷鍋滄鍘熷洜锛歚宸插埌杈剧┖鐧藉垎椤礰锛沀I 鏄犲皠涓衡€滃凡鍒拌揪鍒楄〃鏈〉鈥濄€?
- 鐩稿绾?`242` 鐪嬭繃 / `34` 鎯崇湅鐨勫巻鍙茶繎浼煎熀绾匡紝涓ら」鍧囧鍔?`2`锛涙湰璁板綍閲囩敤鏈鍏紑椤甸潰鐨勫疄鏃剁粨鏋滐紝涓嶅洖濉棫鍩虹嚎銆?
- 鍏叡杩炴帴鏈姹傜櫥褰曪紝鍥犳娌℃湁瑙﹀彂 Cookie 缁窇锛涘彲瑙?Cookie 杈撳叆鍦ㄥ惎鍔ㄥ墠鍚庨暱搴﹀潎涓?`0`銆?

### 160-target 浼氳瘽涓庤鏁拌涔?

- session锛歚ecbb40ee00384b0c82dcad30559df1d4`
- seed title锛歚douban:1291879`
- seed person锛歚derived:6buR5rO95piO`
- 椤甸潰鍚屾椂鍙锛氱洰鏍?`160`銆佸疄闄呰繑鍥?`192`銆佸綋鍓嶉閬撳€欓€夋睜銆佸尮閰嶃€佹湰鎵瑰彲瑙併€佸綋鍓嶆壒娆°€?
- 鍊欓€夋睜锛氱數褰?`85`銆佸墽闆?`54`銆佸姩婕?`53`锛涘悎璁?`192`銆?
- 鍖归厤锛氱數褰?`84`銆佸墽闆?`54`銆佸姩婕?`53`銆?
- 鍒濆鏈壒鍙锛氫笁涓閬撳潎涓?`24`銆?
- 璇箟淇濇寔鐙珛锛歚target=160` 鏄姹傜洰鏍囷紝`returned=192` 鏄繑鍥炲€欓€夋€婚噺锛宍pool` 鏄閬撳€欓€夋睜锛宍matched` 鏄閬撳尮閰嶉噺锛宍visible` 鏄綋鍓嶆壒娆￠噺銆?
- 鍔ㄦ极姹犲叡 `53` 椤癸紝鍏ㄩ儴 `media_type=鍔ㄦ极` 涓斿甫 `鍔ㄦ极鍓ч泦` 鏍囩锛涙湭鍙戠幇鐢靛奖/鍔ㄧ敾鐗囨爣璁帮紝鍥犳娌℃湁鍔ㄧ敾鐢靛奖娣峰叆銆?
- 鍓ч泦姹犲叡 `54` 椤癸紝鍙よ鏍囪 `0/54`锛屼笉瀛樺湪鍙よ涓诲銆?

### 杩炵画鎹㈡壒

- 鐢靛奖锛氭壒娆?`1/2/3/4` 鍒嗗埆杩斿洖 `24/24/24/12` 椤癸紱绗洓鎵硅€楀敖锛涘悇鎵逛箣闂撮噸澶嶆爣棰?`0`銆?
- 鍓ч泦锛氭壒娆?`1/2/3/4` 鍒嗗埆杩斿洖 `24/24/6/0` 椤癸紱绗笁鎵硅€楀敖锛岀鍥涙壒涓虹┖锛涜€楀敖鍓嶉噸澶嶆爣棰?`0`銆?
- 鍔ㄦ极锛氭壒娆?`1/2/3/4` 鍒嗗埆杩斿洖 `24/24/5/0` 椤癸紱绗笁鎵硅€楀敖锛岀鍥涙壒涓虹┖锛涜€楀敖鍓嶉噸澶嶆爣棰?`0`銆?
- 鏈€缁堟挙鍥炲埌鍔ㄦ极绗?`3` 鎵癸紝鏍囬涓猴細`澶╁厓绐佺牬绾㈣幉铻哄博`銆乣闄嶄笘绁為€氾細鏈€鍚庣殑姘斿畻`銆乣鐖憋紝姝讳骸鍜屾満鍣ㄤ汉`銆乣闆惧北浜旇`銆乣鐏电`銆?

### Refresh / Back 鎭㈠涓庢祻瑙堝櫒瀹¤

1. 閫氳繃浣滃搧璇︽儏 鈫?鍙ｅ懗瀹囧畽 鈫?鈥滃甫鍏ヤ粖鏅氭帹鑽愨€濈殑鍙娴佺▼锛屽皢 `闄嶄笘绁為€氾細鏈€鍚庣殑姘斿畻` 鍔犲叆鍊欓€夋墭鐩樸€?
2. 鍦?`/tonight/anime-series` 鐨勭 `3` 鎵规粴鍔ㄥ埌 `scrollY=900`锛涢〉闈㈤珮 `2031`锛寁iewport 楂?`720`銆?
3. 浠庨〉闈㈠唴鍙浣滃搧閾炬帴鎵撳紑 `/title/douban:1938084`锛涚寮€棰戦亾鍚庡畨鍏ㄧ姸鎬佹姇褰变负 `animeBatch=3`銆乣animeScroll=900`銆乣candidateTrayCount=1`銆?
4. 鍒锋柊璇︽儏椤靛悗 route 浠嶄负 `/title/douban:1938084`锛屼笖瀹¤缁撴灉锛歚brokenImages=[]`銆乣externalImages=[]`銆乣overflowNodes=[]`銆乣focusFailures=[]`銆乣emptyMain=false`銆?
5. 娴忚鍣ㄨ繑鍥炲悗 route 涓?`/tonight/anime-series`锛岄〉闈㈠彲瑙佺洰鏍?`160`銆佸疄闄呰繑鍥?`192`銆佹湰鎵瑰彲瑙?`5`銆佸綋鍓嶆壒娆?`3`锛沗scrollY=900`锛屽畨鍏ㄧ姸鎬佹姇褰变粛涓?`animeBatch=3`銆乣animeScroll=900`銆乣candidateTrayCount=1`銆?

### Task 5 鍙戠幇骞舵寜 TDD 淇鐨勭己闄?

1. 鍚屾瀹屾垚鍗＄墖鍙樉绀烘€绘潯鐩?鎴愬姛椤?澶辫触椤碉紝涓嶈兘鍖哄垎鐪嬭繃涓庢兂鐪嬶紱鐜版樉绀虹湅杩囥€佹兂鐪嬪強鍒嗛〉缁撴灉銆?
2. 160-target 浼氳瘽鍦ㄥ€欓€夌敓鎴愬悗涓㈠け鍏ㄥ眬 `target/returned`锛涚幇閫氳繃鎸佷箙鍖?`candidate_counts` 骞跺湪浼氳瘽鍒涘缓/鎭㈠鍝嶅簲涓繑鍥烇紝Tonight 鏄惧紡灞曠ず鍏」璁℃暟銆?
3. Router 绂诲紑椤甸潰鏃跺厛鍐欐粴鍔ㄤ綅缃紝闅忓悗 store subscriber 浠ラ檲鏃?`scrollByRoute` 瑕嗙洊璇ュ€硷紱鐜扮敱 router 鎶婃粴鍔ㄤ繚瀛樹簨浠?dispatch 鍒?store锛屽啀缁熶竴鎸佷箙鍖栥€?

### 闅愮涓庨檺鍒?

- 鏈鏈粠娴忚鍣?profile銆丆ookie 鏁版嵁搴撱€佺鐩?Cookie銆佺幆澧冭浆鍌ㄣ€佽姹傚ご銆佹寔涔呯姸鎬佹垨 sessionStorage 璇诲彇 Cookie锛涗篃鏈鏌?sessionStorage 鏉ユ仮澶?Cookie銆?
- Cookie 鍙繚鐣欏湪鍙杈撳叆瀵瑰簲鐨勫悓鏍囩椤典細璇濊矾寰勶紱鏈杈撳叆濮嬬粓涓虹┖銆?
- 娴忚鍣ㄧ姸鎬佹牳瀵逛粎杩斿洖 allowlisted 鎶曞奖锛歳oute銆佸姩婕壒娆°€佸姩婕粴鍔ㄤ綅缃€佸€欓€夋墭鐩樻暟閲忥紱鏈鍑哄畬鏁磋繍琛屾椂鐘舵€併€?
- 鍙鍥剧墖闂ㄧ缁х画瑕佹眰鍚屾簮 `/media/*`锛涘埛鏂板璁＄殑澶栭摼鍥剧墖涓庢崯鍧忓浘鐗囧潎涓?`0`銆?
- 澶栭儴闄愬埗浠呬负锛氬叕寮€杩炴帴鏈Е鍙戠櫥褰曪紝鎵€浠ユ棤娉曞湪涓嶆彁渚涚敤鎴?Cookie 鐨勫墠鎻愪笅瀹炴祴 `needs_cookie` 缁窇鍒嗘敮锛涘叕寮€鏃?Cookie 鍚屾鏈韩宸插畬鏁撮€氳繃銆?

## Task 5 review fixes 鈥?final-code gate (2026-07-12)

### Review findings closed with TDD

1. **Unknown legacy recommendation target:** a deliberately downgraded legacy session now restores `candidate_counts.target_size` as JSON `null` instead of inventing `0`; its exact `returned_size` is still recomputed from the restored channel pools. The V3 store and app reducer preserve that unknown value and Tonight renders `鐩爣 鈥擿. A newly created/metadata-bearing session continues to render exact values (`鐩爣 160`, `瀹為檯杩斿洖 192`).
2. **Stale departure-scroll ownership:** the router's pending departure marker is now owned by the navigation generation. A blocked, stale, or throwing navigation releases only its own marker, while an overlapping newer navigation retains ownership. The regression scenario `slow -> blocked -> real` saves the fresh `/home` scroll value `55` before the real route commits.
3. **390px Universe roster compression discovered by the fresh gate:** the first final-code pass exposed nine vertically compressed roster entries. A focused failing CSS contract was added before changing production CSS; mobile roster entries now retain a readable bounded width and scroll horizontally inside their own roster without document-level horizontal overflow.

### Dedicated final-code service and live sync

- Service: `CINESCOPE_UI_VERSION=v3` (explicit opt-in), `127.0.0.1:7875`, data directory `output/task5-acceptance-data`.
- Browser origin: `http://task5-review-final-20260712.localhost:7875`.
- Accepted recommendation session: `ecbb40ee00384b0c82dcad30559df1d4`; target `160`; returned `192`; anime batch `3`.
- Public sync profile: `https://www.douban.com/people/<your-douban-id>/`.
- Final sync job: `d6574a3aed8649b3a9e0be45c3ef2c45`, state `complete`.
- Actual live result: `280` items, `244` watched/collect, `36` wanted/wish, `22` successful pages, `0` failed pages; visible stop reason `宸插埌杈惧垪琛ㄦ湯椤礰. This is two more watched and two more wanted than the approximate historical `242/34` baseline, so the live values are authoritative for this gate.

### Four-viewport principal-route matrix

Principal routes: `/tonight`, `/tonight/movie`, `/tonight/series`, `/tonight/anime-series`, `/title/douban:1291879`, `/person/derived:6buR5rO95piO`, `/universe`, `/library`, `/taste`, `/health`.

| Viewport | Rows passed | Broken images | External images | Overflow nodes | Focus failures | Empty main | Horizontal scroll | Rail / bottom nav |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| 1440x900 | 10/10 | 0 | 0 | 0 | 0 | 0 | 0 | rail visible / bottom hidden |
| 1280x800 | 10/10 | 0 | 0 | 0 | 0 | 0 | 0 | rail visible / bottom hidden |
| 1024x768 | 10/10 | 0 | 0 | 0 | 0 | 0 | 0 | rail visible / bottom hidden |
| 390x844 | 10/10 | 0 | 0 | 0 | 0 | 0 | 0 | rail hidden 10/10 / bottom visible 10/10 |
| **Total** | **40/40** | **0** | **0** | **0** | **0** | **0** | **0** | mobile contract passed |

The four Tonight routes produced 16 count-line rows. At `/tonight/anime-series`, all four viewports visibly showed `鐩爣 160`, `瀹為檯杩斿洖 192`, `鍊欓€夋睜 53`, `鍖归厤 53`, `鏈壒鍙 5`, and `褰撳墠鎵规 3`, with zero count-line overflow. `/health` visibly showed the long privacy/help line `榛樿鑷姩缈婚〉鍒版湯椤碉紱瀹夊叏涓婇檺 250 椤点€侰ookie 浠呬繚鐣欏湪褰撳墠鏍囩椤典細璇濅腑銆俙, the sync line `鏉＄洰 280 路 鐪嬭繃 244 路 鎯崇湅 36 路 鎴愬姛椤?22 路 澶辫触椤?0`, and `宸插埌杈惧垪琛ㄦ湯椤礰 at every viewport, with zero overflow.

Machine-readable and visual evidence:

- `output/task5-acceptance/task5-review-final-evidence.json` 鈥?aggregate summary plus all 40 route/viewport rows.
- `output/task5-acceptance/final-code-gate/evidence.json` 鈥?raw final-code audit rows.
- `output/task5-acceptance/final-code-gate/<viewport>/*.png` 鈥?40 route screenshots.
- `output/task5-acceptance/final-code-gate/focus/*-tonight-counts.png` and `*-health-sync.png` 鈥?four-view count and Health crops.
- `output/task5-acceptance/final-code-gate/focus/task5-final-counts-health-contact-sheet.png` 鈥?reviewed contact sheet.

### Privacy and remaining external limitation

The Cookie field remained visibly empty. No Cookie was read from browser/session storage, a browser profile, disk, environment dumps, request headers, or persisted state; no storage was inspected to recover one. The accepted session was loaded through a same-origin API read and an allowlisted in-memory store dispatch only. Visible images remained fail-closed to same-origin `/media/*`. Public sync did not request authentication, so the visible `needs_cookie` resume branch could not be completed without a user-supplied Cookie; no Cookie was sourced or fabricated.

## Task 5 upgrade-path re-review 鈥?explicit null precedence (2026-07-12)

### Upgrade-path contract

A previous Task 5 build could persist a same-session `candidate_counts.target_size` value of `0`. When the restored server payload explicitly says `target_size: null`, that present null is now authoritative and clears any cached numeric value. A missing `target_size` property still uses the existing safe same-session fallback, while a valid numeric server value such as `160` remains authoritative. Unknown is therefore preserved as `null` in state and `鐩爣 鈥擿 in Tonight; it is never represented as `0`.

The integration regression persists a same-session target of `0`, restores it through the real store projection, and then applies three server shapes in order:

1. explicit `target_size: null` 鈫?all three channels become `null` and Tonight renders `鐩爣 鈥擿, never `鐩爣 0`;
2. exact `target_size: 160` 鈫?state and Tonight return to exact `160`;
3. absent `target_size` after that exact response 鈫?the safe exact cached fallback remains `160`.

The RED run failed with `explicit null did not clear cached target for movie: {"target_size":0,"returned_size":192}`. The minimal implementation only adds own-property-aware precedence for the explicit null case in `app.js`.

### Recaptured final-code browser evidence

- Evidence generated: `2026-07-11T20:30:59.282Z` (`2026-07-12 04:30:59 +08:00`).
- Service: explicit-opt-in V3 on `127.0.0.1:7875`, data directory `output/task5-acceptance-data`.
- Browser origin: `http://task5-upgrade-final2-20260712.localhost:7875`.
- Exact-count matrix session: `7e5061e80be74395bb6a6b1ba876271e`, target `160`, returned `192`, anime batch `3`.
- Legacy-dash browser session: `da5be0b35dd84973b9cb5a2419709a68`; it held a cached numeric target before reload, was deliberately downgraded on the server to omit historical candidate-count metadata, restored as API `target_size: null`, and visibly rendered `鐩爣 鈥擿 with `瀹為檯杩斿洖 192`, pool `53`, matched `53`, visible `5`, batch `3`. The automated integration regression covers the specifically reported cached-`0` predecessor state.

The same ten principal routes were recaptured at `1440x900`, `1280x800`, `1024x768`, and `390x844`. All 40 rows use final viewport screenshots and passed:

```text
row_count=40
pass_count=40
failure_count=0
broken_images=0
external_images=0
overflow_nodes=0
focus_failures=0
empty_main_rows=0
horizontal_scroll_rows=0
mobile_rail_hidden_rows=10
mobile_bottom_nav_visible_rows=10
tonight_rows=16
viewport_screenshots=40
```

At `/tonight/anime-series`, all four viewports again exposed the exact six-value line: `鐩爣 160`, `瀹為檯杩斿洖 192`, `鍊欓€夋睜 53`, `鍖归厤 53`, `鏈壒鍙 5`, `褰撳墠鎵规 3`. The 390px Universe roster retained nine entries with a minimum entry width of `288px`, no document-level horizontal scroll, and no overflow finding.

Evidence paths:

- `output/task5-acceptance/task5-upgrade-path-final-evidence.json`
- `output/task5-acceptance/upgrade-path-final-code-gate/evidence.json`
- `output/task5-acceptance/upgrade-path-final-code-gate/<viewport>/*.png` 鈥?40 final viewport screenshots
- `output/task5-acceptance/upgrade-path-final-code-gate/focus/<viewport>-tonight-counts.png` 鈥?four exact-count crops
- `output/task5-acceptance/upgrade-path-final-code-gate/focus/legacy-target-dash-final.png` 鈥?focused authoritative-null crop
- `output/task5-acceptance/upgrade-path-final-code-gate/focus/upgrade-path-counts-contact-sheet.png` 鈥?reviewed exact/legacy contact sheet

No new public sync was started for this upgrade-only re-review; the previously recorded `280 / 244 / 36 / 22 / 0` live result and its provenance remain unchanged. No Cookie was entered, sourced, or inspected. Browser Cookie/profile/storage data was not read, and no missing media was fabricated.

## Rollout Task 6 鈥?performance and media coverage gate (2026-07-12)

### Service, fixture, and static contracts

- V3 remained explicit opt-in: `CINESCOPE_UI_VERSION=v3`; the default legacy rollback path was not changed.
- Dedicated service: `127.0.0.1:7886`; dedicated data directory: `output/task6-acceptance-data`.
- The Task 6 database was a byte-identical copy of `output/task5-acceptance-data/cinescope.db` at startup; both SHA-256 values were `28952d34cdbe43af03b3e1cec1d6b79d8bf9c172022699c15aca4466827f2700`.
- Accepted session `ecbb40ee00384b0c82dcad30559df1d4` was reused through a same-origin API read and the allowlisted reducer/persistence write path. The automation did not inspect Cookie data, an existing browser profile, any pre-existing local/session storage value, or source secrets; it wrote only the allowlisted UI-state projection needed for full-document reload restoration.
- Detail fixture: `/title/douban:1291879` (`缃楃敓闂╜).
- `tests/test_performance_contract.py` added five dedicated static/scope contracts. They all passed on their first run (`5 passed`), characterizing behavior already present at the required base commit: `MAX_INITIAL_CARDS=9`, `casts.slice(0, 8)` with directors, priority-0 portrait prefetch, decoded same-origin `/media/*` insertion, and exact diagnostics scopes. There was therefore no invented RED and no production behavior change.

### Warm-cache full-document reload measurements at 1440脳900

Measurement used a fresh Task 6 Chrome profile with cache enabled. `Page.addScriptToEvaluateOnNewDocument` installed buffered `PerformanceObserver` collectors for `largest-contentful-paint` and `longtask` before priming or measuring. Each route was primed once, then measured through three `Page.reload` full-document reloads; every measured `PerformanceNavigationTiming.type` was `reload`. DOM readiness was checked separately and was not substituted for LCP.

| Route | Warm LCP runs (ms) | Warm DCL runs (ms) | Same-origin `/media/*` transfer bytes | `/media/*` encoded body bytes | Long tasks / maximum | Gate |
|---|---|---|---:|---:|---|---|
| `/tonight` | `44 / 32 / 32` (max `44`) | `14.1 / 14.0 / 14.5` (max `14.5`) | `0 / 0 / 0` | `0 / 0 / 0` | `0 / 0 ms` | PASS |
| `/title/douban:1291879` | `32 / 36 / 24` (max `36`) | `14.4 / 15.2 / 13.2` (max `15.2`) | `0 / 0 / 0` | `0 / 0 / 0` | `0 / 0 ms` | PASS |

- Gate: every warm LCP was `<=2500 ms`; no observed long task exceeded `200 ms`.
- The `/tonight` LCP candidate was the final Tonight intro heading. The detail reload LCP candidate was the initial shell heading; the final detail DOM was independently required to settle before evidence capture. The recorded values are observer LCP values, not DOM-ready proxies.
- Zero `/media/*` requests and zero bytes reflect the fixture's actual zero ready media assets; they are not a claim that real media was compressed or hidden.
- Since all measured gates passed, Task 6 made no production performance change and triggered no RED/GREEN optimization cycle.

### Rendered browser media coverage and designed fallbacks

Scope: one representative settled warm reload from each audited route for coverage, plus all six measured reloads for browser failure totals. A 鈥渕issing image element failure鈥?means a rendered media frame marked `ready` without an `<img>`, or a frame still marked `loading` after settle. A designed CSS fallback is reported separately and is not treated as a failure.

| Route / kind | Rendered occurrences | Real decoded `<img>` | Designed fallback | Real coverage |
|---|---:|---:|---:|---:|
| `/tonight` posters | 15 | 0 | 15 | 0% |
| Detail posters | 9 | 0 | 9 | 0% |
| Detail portraits | 4 | 0 | 4 | 0% |
| Detail backdrop | 1 | 0 | 1 | 0% |
| **Combined posters** | **24** | **0** | **24** | **0%** |
| **Combined portraits** | **4** | **0** | **4** | **0%** |

- All poster, portrait, and backdrop fallback status labels were exactly `鏈湴绱犳潗缂哄け`.
- `/tonight` designed poster labels (15 occurrences; 14 unique labels because the hero repeats one shelf title): `澶╁厓绐佺牬绾㈣幉铻哄博 路 浣滃搧娴锋姤`, `瀹岀編鐨勬棩瀛?路 浣滃搧娴锋姤`, `鎬墿 路 浣滃搧娴锋姤`, `鏁欑埗 路 浣滃搧娴锋姤`, `鏉€浜哄洖蹇?路 浣滃搧娴锋姤`, `娑堝け鐨勭埍浜?路 浣滃搧娴锋姤`, `鐏电 路 浣滃搧娴锋姤`, `鐖憋紝姝讳骸鍜屾満鍣ㄤ汉 路 浣滃搧娴锋姤`, `缇庝附浜虹敓 路 浣滃搧娴锋姤`, `鑺辨牱骞村崕 路 浣滃搧娴锋姤`, `閲嶅簡妫灄 路 浣滃搧娴锋姤`, `闄嶄笘绁為€氾細鏈€鍚庣殑姘斿畻 路 浣滃搧娴锋姤`, `闄嶄复 路 浣滃搧娴锋姤`, `闆惧北浜旇 路 浣滃搧娴锋姤`.
- Detail designed poster labels: `涓冩澹?路 浣滃搧娴锋姤`, `淇″彿 路 浣滃搧娴锋姤`, `濂囧阀璁＄▼杞?路 浣滃搧娴锋姤`, `鎺ф柟璇佷汉 路 浣滃搧娴锋姤`, `娌宠竟鐨勯敊璇?路 浣滃搧娴锋姤`, `婕暱鐨勫鑺?路 浣滃搧娴锋姤`, `缃楃敓闂?路 浣滃搧娴锋姤`, `鑷村懡榄旀湳 路 浣滃搧娴锋姤`, `闅愮鐨勮钀?路 浣滃搧娴锋姤`.
- Detail designed portrait labels: `涓夎埞鏁忛儙 路 浜虹墿鑲栧儚`, `浜敽瀛?路 浜虹墿鑲栧儚`, `蹇楁潙涔?路 浜虹墿鑲栧儚`, `榛戞辰鏄?路 浜虹墿鑲栧儚`; designed backdrop label: `缃楃敓闂?路 浣滃搧鑳屾櫙`.
- Across all six measured reloads: broken visible images `0`, external/non-`/media/*` visible images `0`, pending visible images `0`, and missing-image-element failures `0`. The built-in browser audit also reported broken images `0` and external images `0` on every run.
- The insertion contract remains unchanged: a visible `<img>` must be same-origin `/media/*` and only replaces its fallback after load, `decode()`, and `naturalWidth > 0`.

### Diagnostics scopes and identity canary

The post-measurement `/api/v2/diagnostics` response reported:

- Stored media totals: `assets_total=0`, `bytes=0`.
- Bounded recent-batch poster audit: `total=256`, `ready=0`, `degraded=0`, `ambiguous=0`, `missing=256`.
- Audit window scope: `recent_recommendation_batches`; ordering `created_at_desc_then_id_desc`; `batch_limit=32`; `row_limit=256`; `selected_batches=32`; `rows_audited=256`; `truncated=true`.
- Wrong-identity count: `0`, with exact scope `global_historical_identity_rejected_hard_conflicts`.
- Attribution limit: `recommendation_media_identity_attribution=unavailable_without_stable_foreign_key`. The wrong-identity value is a global historical hard-conflict canary and is not attributed to the visible session. The bounded media totals are likewise a recent-batch window, not a visible-page-only total.

The required zero browser failures and zero wrong-identity canaries passed. Real poster and portrait coverage remained zero and is reported directly rather than disguised by the designed fallbacks.

### Machine-readable evidence

- `output/task6-acceptance/service.json` 鈥?dedicated service, data copy hashes, and zero copied media files.
- `output/task6-acceptance/fixture.json` 鈥?accepted session and detail fixture summary.
- `output/task6-acceptance/performance.json` 鈥?raw observer entries, navigation timing, resource timing, CDP media events, per-run browser media audits, and gates.
- `output/task6-acceptance/diagnostics.json` 鈥?raw post-measurement diagnostics response.
- `output/task6-acceptance/acceptance-summary.json` 鈥?aggregate metrics, coverage, failures, and exact scope statements.
- `output/task6-acceptance/evidence-validation.json` 鈥?machine validation of all required gates and non-fabrication assertions.
- `output/task6-acceptance/measure-performance.mjs` 鈥?the exact CDP measurement harness used for the final evidence.

## Task 6 review closure 鈥?route-specific meaningful paint (2026-07-12)

The original Task 6 detail LCP entries were valid browser LCP entries but identified only the generic initial `#shell-title`. They did not, by themselves, timestamp the first meaningful detail paint. Fresh evidence therefore retains standard LCP while adding a route-specific pre-navigation observer; the standard detail LCP is no longer used alone to claim meaningful detail readiness.

### Pre-navigation method

The CDP harness still installs through `Page.addScriptToEvaluateOnNewDocument` before prime or measured navigation. In the same injected source it now:

1. watches for the intended committed route root and keeps a frame-level detector active while CSS entry animation progresses;
2. requires the exact final route, non-empty intended content, positive rendered geometry, matching route identity, required copy/sections, and route-specific content children;
3. records `routeCommitMs` at the first valid visible route-root commit;
4. revalidates the route after two `requestAnimationFrame` callbacks and records `routeContentPaintMs` as the meaningful painted-route proxy;
5. records `routeSettleMs` only when the same proof remains valid, `document.readyState=complete`, no element is `aria-busy=true`, no media frame remains `loading`, and route-root opacity is at least `0.99`.

Route proofs:

- Tonight: root `.tonight-page`; identity `.tonight-intro__title` = `浠婃櫄锛屽彧鐪嬪€煎緱寮€濮嬬殑銆俙; required copy includes `鐩爣 160` and `瀹為檯杩斿洖 192`; required route structures are present; `.title-card` count is `14`; final route is `/tonight`.
- Detail: root `.detail-page`; identity `.detail-hero__title` = `缃楃敓闂╜; required copy includes `缃楃敓闂╜, `婕旇亴浜哄憳`, and `鏈湴鍏宠仈`; `#overview`, `#people`, and `#relations` are present; `.person-card` count is `4`; final route is `/title/douban:1291879`.
- Every paint proof records the exact selector, text/identity proof, required-text and required-selector results, final route, content count, computed style, and bounding rect. Tonight rects were `1266.625脳2017.703125`; detail rects were `1266.625脳3079.984375`, all with positive visible geometry.

### Fresh warm-cache full-reload evidence

Each route was primed once and then measured through three cache-enabled `Page.reload` full-document reloads at `1440脳900`. All measured navigation types were `reload`.

| Route / metric | Raw runs (ms) | Min | Median | Max | Gate |
|---|---|---:|---:|---:|---|
| `/tonight` standard LCP | `32 / 32 / 32` | 32.0 | 32.0 | 32.0 | PASS |
| `/tonight` route commit | `67.6 / 61.5 / 74.1` | 61.5 | 67.6 | 74.1 | proof present |
| `/tonight` route-content paint | `71.7 / 64.2 / 80.2` | 64.2 | 71.7 | 80.2 | PASS |
| `/tonight` route settle | `71.7 / 64.3 / 80.4` | 64.3 | 71.7 | 80.4 | PASS |
| Detail standard LCP | `24 / 36 / 32` | 24.0 | 32.0 | 36.0 | browser LCP retained |
| Detail route commit | `78.4 / 99.9 / 86.8` | 78.4 | 86.8 | 99.9 | proof present |
| Detail route-content paint | `94.3 / 116.0 / 103.0` | 94.3 | 103.0 | 116.0 | PASS |
| Detail route settle | `317.6 / 339.1 / 325.8` | 317.6 | 325.8 | 339.1 | PASS |

- Meaningful route-content paint gate: every run `<=2500 ms`.
- Route settle gate: every run `<=2500 ms`.
- Existing long-task gate: six runs, maximum `0 ms`, therefore no task above `200 ms`.
- Standard LCP gate remains passing, but all three detail LCP candidates remain `H1#shell-title`; no detail LCP candidate was fabricated or relabeled.
- Detail paint proofs captured the first visible entry-animation frames at opacity about `0.074`; settle proofs were separately delayed until opacity about `0.992`, with document complete, no busy state, and zero loading media frames.
- The new methodology passed without exposing a production bottleneck, so no production regression or implementation change was made.

### Unchanged coverage and scopes

- Same-origin `/media/*` requests, transfer bytes, and encoded body bytes remained `0`; the fixture still has zero ready media assets.
- Real coverage remains posters `0/24`, portraits `0/4`, backdrop `0/1`; all are honestly reported designed CSS fallbacks.
- Browser broken/external/pending/missing-image-element failures remain `0` across all six runs.
- Diagnostics remain `assets_total=0`, `bytes=0`; bounded recent-batch poster audit `0 ready / 256 missing`; wrong-identity canary `0` with scope `global_historical_identity_rejected_hard_conflicts` and no visible-session attribution.
- `output/task6-acceptance/evidence-validation.json` schema 2 contains 25 passing checks, including required route selector/identity/timestamps/geometry, ordering, content-paint and settle budgets, honest shell LCP retention, raw summary statistics, zero media fabrication, and exact diagnostics scopes.

## Rollout Task 8 鈥?final verification and completion evidence (2026-07-12)

### Bound source and isolated services

- Final code under test: `847a70b4a447fa9d26b17b5e5be1326dc65e218c` (`feat: make cinescope v3 the default experience`).
- Default V3 ran on `127.0.0.1:7891` with `CINESCOPE_UI_VERSION` absent, dedicated data directory `output/task8-acceptance-data`, and the V3 asset shell present. This directly verifies the default switch rather than an explicit V3 opt-in.
- Rollback ran separately on `127.0.0.1:7892` with `CINESCOPE_UI_VERSION=legacy`. Port `7860` was not touched. Both Task 8 ports were released at shutdown.
- Fixed resources: session `ecbb40ee00384b0c82dcad30559df1d4`, title `douban:1291879`, person `derived:6buR5rO95piO`.

### Automated and hygiene gates

```text
python -m unittest discover -s tests -v
Ran 601 tests in 86.615s
OK
```

- Recursive JavaScript syntax validation covered all `23` files under `src/douban_recommender/ui/js/**/*.js`; every `node --check` exited successfully.
- `git diff --check` passed before documentation work and again after this section was added.
- The required source/test/README/acceptance placeholder scan returned zero matches, so there was no unintended placeholder to classify.
- Raw logs: `output/task8-acceptance/unittest-final.log`, `output/task8-acceptance/node-check.log`, and `output/task8-acceptance/hygiene.log`.

### Fresh final-code browser smoke

The Codex in-app browser collected a new source-bound matrix; prior Task 4鈥? JSON was not counted as final-code smoke. Each route settled with the intended route, non-empty main content, no `aria-busy=true`, and a viewport screenshot.

| Viewport | Route | Audit | Navigation contract |
|---|---|---|---|
| `1440脳900` | `/tonight` | PASS | desktop rail visible; bottom nav hidden |
| `1440脳900` | `/tonight/anime-series` | PASS | desktop rail visible; bottom nav hidden |
| `1440脳900` | `/title/douban:1291879` | PASS | desktop rail visible; bottom nav hidden |
| `1440脳900` | `/person/derived:6buR5rO95piO` | PASS | desktop rail visible; bottom nav hidden |
| `1440脳900` | `/health` | PASS | desktop rail visible; bottom nav hidden |
| `390脳844` | `/tonight` | PASS | desktop rail hidden; bottom nav visible |
| `390脳844` | `/tonight/anime-series` | PASS | desktop rail hidden; bottom nav visible |
| `390脳844` | `/title/douban:1291879` | PASS | desktop rail hidden; bottom nav visible |
| `390脳844` | `/person/derived:6buR5rO95piO` | PASS | desktop rail hidden; bottom nav visible |
| `390脳844` | `/health` | PASS | desktop rail hidden; bottom nav visible |

For all `10/10` rows, `window.__CINESCOPE_AUDIT__()` returned empty `brokenImages`, `externalImages`, `overflowNodes`, and `focusFailures`; `emptyMain=false`; the document had no horizontal scrolling.

On `/tonight/anime-series`, visible input `鏇村亸娓╂殩銆佽妭濂忚垝缂揱 was submitted through **鎸夊師鍥犳崲涓€鎵?*. The page changed from batch `3` with five visible titles to batch `4` with status `涓嬩竴鎵瑰凡灏辩华銆俙 and an empty exhausted batch, proving a real server-backed transition rather than a visual-only change.

Refresh restoration used the visible route flow: the page was scrolled, navigated to Health through the rail, returned with browser Back, and then full-document reloaded. The route remained `/tonight/anime-series`; batch `4` remained active; all three shelf count/item projections were identical before and after reload; the route-max scroll position restored exactly at `738px` both before and after the full reload. The initial attempted `867px` position was clamped by the rendered page maximum and is not reported as a failed restoration.

No Cookie was entered. Visible Cookie fields stayed empty. The run did not read browser Cookie data, profiles, local/session storage, disk Cookie files, environment dumps, request headers, or hidden storage. The fixed session was prepared by writing a source-derived allowlisted UI-state projection; no browser storage value was read.

### Legacy rollback and data integrity

The legacy root loaded with title `CineScope Studio锛氳眴鐡ｇ浜哄奖瑙嗙瓥灞曞櫒`, heading `CineScope Studio`, non-empty content, and no V3 asset reference. Its visible Cookie textarea remained empty.

```text
SHA-256 before legacy: a31e07221893da3c1e18b33c7d26a67f5517906040b91c9cf011162680897670
SHA-256 after legacy:  a31e07221893da3c1e18b33c7d26a67f5517906040b91c9cf011162680897670
```

The hashes are identical, proving that selecting the legacy UI did not change `output/task8-acceptance-data/cinescope.db`.

### Performance/media provenance and evidence paths

Task 8 does not relabel historical timing as a fresh measurement. The retained performance and media conclusion comes from Task 6 commits `3e53e07061fd2213fc8f67580f6ab114c1186313` and `c427f4a535a0b913b34f5a5418a06afb80de2607`, recorded in `output/task6-acceptance/verification.json`. Its warm-cache route-content paint and settle gates passed. Real media coverage remains honestly unchanged: posters `0/24`, portraits `0/4`, backdrop `0/1`; designed CSS fallbacks are not counted as broken images and are not described as real media.

- Final machine evidence: `output/task8-acceptance/final-evidence.json`.
- Fresh route rows and restoration details: `output/task8-acceptance/browser-evidence.json`.
- Fresh screenshots: `output/task8-acceptance/screenshots/1440x900`, `output/task8-acceptance/screenshots/390x844`, and `output/task8-acceptance/screenshots/legacy`.
- Historical-only provenance is enumerated under `old_evidence_provenance` in the final machine evidence; those older JSON files are not substitutes for the Task 8 smoke matrix.

## Final review fix wave closure (2026-07-12)

Fresh verification is bound to code commit `0fed4e5df29f732ba8d1dab7d2ba1c0edd9058c0`; no Task 8 JSON is reused as evidence for this fix wave.

- Fixed-URL V3 HTML shells and the complete `/assets/v3/*` graph now return `Cache-Control: no-cache, no-store, must-revalidate`. Content-addressed `/media/*` remains `public, max-age=31536000, immutable`. Therefore the documented normal origin `http://127.0.0.1:7861` can receive upgraded code without changing hostnames.
- Explicit legacy mode now serves the legacy shell for all legal frontend deep links, including `/tonight/anime-series`, `/title/douban:1291879`, and `/person/derived:6buR5rO95piO`. Encoded traversal, encoded service roots, `/api/*`, missing `/assets/*`, and invalid `/media/*` remain excluded.
- Recovery now captures the pre-render live store, merges only its sanitized route scroll values into the last stable snapshot, preserves sanitized `candidate_counts.target_size` and `returned_size` (including explicit `target_size: null`), and continues dropping failed-render candidate tray and command-lens mutations. The returned recovery state, retry callback, and remembered stable state use the same merged scroll.
- Strict TDD RED/GREEN transcripts are under `output/final-review-fix/` for cache headers, legacy deep links, and recovery scroll/counts. Focused verification passed `30` tests; the complete suite passed `604` tests; all `23` V3 JavaScript files passed `node --check`.
- Fresh V3 ran with `CINESCOPE_UI_VERSION` absent on `127.0.0.1:7911` and a dedicated data copy. HTTP evidence covers root HTML, deep HTML, `app.js`, and immutable media. Browser smoke passed `10/10` route/viewport rows at `1440x900` and `390x844`, with empty audit failure arrays, no document horizontal overflow, correct responsive navigation, and an empty visible Cookie field.
- The anime route changed from non-empty batch 1 to a different non-empty batch 2 through the visible reason field and button. Back navigation and full-document refresh retained route, batch, all nine visible titles, and the same settled `520px` scroll.
- At an actual `390x844` browser viewport, the real detail-route H1 was temporarily replaced with `InterstellarDirectorCutRestoredEdition` repeated exactly 24 times. The H1 measured `scrollWidth=179`, `clientWidth=179`; the document measured `scrollWidth=375`, `clientWidth=375`. Reload restored `缃楃敓闂╜; no production hook was added.
- Explicit legacy ran separately on `127.0.0.1:7912`. Root plus the three required deep links rendered the legacy shell in the browser; unsafe and service paths stayed `404`. The dedicated database SHA-256 remained `709fd2ab0b673a1eceea05730cef6d20f68482441ed9f772a62c50e65e3cf3e6` before and after rollback verification.
- Ports `7911` and `7912` were released. Existing listener `127.0.0.1:7860` (PID `15948`) was unchanged. No Cookie was entered, and no browser profile, Cookie store, local/session storage value, request header, environment dump, or hidden state was read.

Machine evidence: `output/final-review-fix/browser-smoke.json`, `batch-refresh.json`, `long-title.json`, `cache-http.json`, `legacy-http.json`, `legacy-browser.json`, `db-hash.json`, `service-cleanup.json`, plus the RED/GREEN and automation logs in the same directory.

## Final edge fix closure 鈥?canonical recovery and Cookie documentation (2026-07-12)

Fresh verification is bound to code commit `d439db8857e6439f7baa451bf906b96100acc8ae` and tree `d02b298e9fd0b3e60e11752d9fc710b39e6e53e1`. Evidence was newly generated under `output/final-edge-fix/`; no earlier final-review or Task 8 artifact is counted as current proof.

- Recovery now captures the sanitized live state before renderer execution, merges live scroll entries after remembered entries with overlap replacement, and sanitizes the merged result into one canonical snapshot capped at `100` routes. Safe scroll retention keeps the last `100` valid records, so a regression containing `100` remembered plus `100` disjoint live routes retains all live routes, including newest `/live-099 = 1099`.
- `renderSafely().previousStable`, the recovery retry payload, and `restoreLastStableState()` are deeply equal but independently cloned projections of that canonical snapshot. Existing `scroll=900`, nullable candidate counts, privacy filtering, and failed-render side-effect discard assertions remain green.
- Strict TDD evidence is `recovery-canonical-red.txt` (`100 != 200`) 鈫?`recovery-canonical-green.txt`, and `readme-cookie-red.txt` (the inaccurate automatic-clear sentence remained) 鈫?`readme-cookie-green.txt`. The focused migration/README run passed `31` tests; full discovery passed `606` tests; all `23` JavaScript files passed `node --check`; `git diff --check` and the placeholder scan passed.
- README now matches `sync.js`: after a sync request the visible textarea and current-tab `sessionStorage` retain the Cookie; disposing/navigating away clears the visible field; returning in the same tab restores it from `sessionStorage`; closing the tab invalidates it. Cookie remains visible-input-only/current-tab-only, is not written to database, disk, cache, logs, or reports, and is not read from browser Profile, request headers, or hidden storage.
- Default V3 ran on `127.0.0.1:7921`. Fresh browser smoke passed `10/10` rows at `1440脳900` and `390脳844` across Tonight, anime Tonight, a real title detail, a person detail, and Health. All audit failure arrays were empty, main content was non-empty, responsive navigation matched each viewport, and the visible Cookie field on Health was empty.
- The anime route changed through the visible reason field and **鎸夊師鍥犳崲涓€鎵?* from non-empty batch `1` (nine titles, hero `鏄熼檯鐗涗粩`) to different non-empty batch `2` (nine titles, hero `鏃犳晫灏戜緺`). Visible navigation Back and a subsequent full-document reload each retained batch `2`, all nine titles, and the settled `1310px` scroll position.
- A fresh `390脳844` long-title proof temporarily replaced the real detail H1 with `InterstellarDirectorCutRestoredEdition` repeated `24` times. The H1 measured `scrollWidth=179`, `clientWidth=179`; the document measured `scrollWidth=375`, `clientWidth=375`; reload restored `鎺ф柟璇佷汉`.
- V3 HTML/assets remained `no-cache, no-store, must-revalidate`, content-addressed media remained immutable, and served `app.js` SHA-256 matched the source file. Explicit legacy ran on `127.0.0.1:7922`; root and three legal deep links rendered the legacy shell, excluded service/unsafe paths stayed `404`, and the dedicated database hash remained `54ea64536d90a5293e127cb54ae41c26c29eef2cbbea6787d287d7eedd4388d2` before and after rollback.
- Ports `7921` and `7922` were released. Existing `127.0.0.1:7860` PID `15948` was unchanged. No Cookie was entered; browser Cookie/profile/storage/request-header/hidden state was not read. Task 6 timing remains historical-only and is not relabeled as a new performance measurement.

Machine evidence: `output/final-edge-fix/final-evidence.json`, `browser-smoke.json`, `batch-refresh.json`, `long-title.json`, `cache-http.json`, `legacy-http.json`, `legacy-browser.json`, `db-hash.json`, `service-cleanup.json`, screenshots, RED/GREEN transcripts, and automation logs in the same directory.

## Final closure fix wave 鈥?six Important findings and uncropped evidence (2026-07-12)

This closure supersedes `output/final-edge-fix/` as current proof. That directory remains historical only; in particular, its general-route mobile PNGs are not accepted because the DPR 1.5 raster was cropped to the CSS viewport dimensions. No screenshot or JSON from that directory is reused by this closure.

### Bound source and fixes

- Evidence source commit: `193b85c5d94b2e9a7c80240fbe59ca979a4f25b1` (`fix: close final review findings`).
- Evidence source tree: `8c34778fd4bb25c29ce94f3443ca5f0743d0be63`.
- Recovery now uses the sanitized pre-render live stable state as the canonical recovery body. Remembered state is only a fallback when live state has no valid active path; remembered/live scroll maps still merge in recency order with live overlap winning, a last-100 cap, independent clones, nullable candidate counts, privacy filtering, the existing `900px` case, and failed-render side effects excluded.
- Scroll persistence sanitizes every valid route before retaining the latest `100`. Updating an existing route deletes and reinserts it in both the reducer and `saveScroll()`, so in-memory and restored state retain the newest live routes.
- Direct overlapping navigation recaptures the latest departure `scrollY` before moving pending generation ownership, including the previously uncovered direct `slow -> real` path.
- V3 sync start and resume share one visible-value/sessionStorage rule: non-empty visible input sets the current-tab value and empty visible input removes it. Clearing the field, resuming, disposing, and remounting no longer revives an older value.
- Explicit legacy rollback remains reachable on legal deep links, but clipboard reads, the one-click clipboard importer, full-header extraction, and header-dump instructions are removed. The visible textarea accepts only a directly pasted `name=value; ...` Cookie string and rejects multiline, prefixed, or explanatory content.
- `audit.js` now exposes visual viewport, DPR, document viewport, fixed bottom-navigation bounds, essential element rects, and clipped-essential results. `evidence_validation.py` validates PNG format and decoded dimensions, one declared capture mode, viewport/DPR geometry, bottom-navigation bounds, essential clipping, artifact hashes/sizes, and the lower-right marker that rejects the known top-left crop regression.

Strict RED/GREEN transcripts for all six findings are under `output/final-closure-fix/tdd/`; the final full-suite, recursive JavaScript syntax, diff hygiene, and placeholder-scan logs are stored beside the browser evidence.

### Fresh screenshot and browser gate

All current screenshots were captured from the bound source through `playwright-core@1.61.1` and system Chrome in fresh, profile-free contexts. The single declared mode is `raw-device-pixels` with `deviceScaleFactor=1`; post-processing is `none` (`cropped=false`, `resized=false`). Requested viewport, `innerWidth/innerHeight`, `visualViewport` size/scale, DPR, decoded PNG size, document viewport, bottom-navigation rect, and essential rects are recorded per capture.

- Desktop captures: requested/inner/PNG `1440x900`, DPR `1`, visual viewport scale `1`.
- Mobile captures: requested/inner/PNG `390x844`, DPR `1`, visual viewport scale `1`; the fixed bottom navigation is visible and fully within `left=0`, `right=390`, `bottom=844`.
- The V3 matrix passed `10/10` rows across `/tonight`, `/tonight/anime-series`, `/title/douban:1291879`, `/person/derived:6buR5rO95piO`, and `/health` at both viewports. Every row had non-empty main content, correct responsive navigation, no broken/external image, no document horizontal overflow, no focus failure, and no clipped essential element.
- Visible images, where present, remain successful same-origin `/media/*`; unavailable media remains a non-image designed fallback. No external image is counted as delivered media.
- Chrome emitted one generic resource-404 console line with no attributable HTTP failure; it is recorded separately as `ignored_generic_resource_404`. The failure-bearing console array is empty.

The anime route changed through the visible reason input from non-empty batch `1` (nine titles) to a different non-empty batch `2` (nine titles). Browser Back and a full-document reload each retained `/tonight/anime-series`, batch `2`, all nine titles, and the settled `1310px` scroll position. The before/after and refresh screenshots use the same DPR-1 raw capture contract.

At a real `390x844` viewport, the detail H1 was temporarily replaced with `InterstellarDirectorCutRestoredEdition` repeated `24` times. The H1 measured `clientWidth=scrollWidth=194`; the document measured `clientWidth=scrollWidth=390`; reload restored `缃楃敓闂╜. The lower-right marker regression fixture separately proves that a DPR raster top-left crop is rejected.

### Cache, legacy, privacy, data, and cleanup

- V3 root/deep-link HTML and served assets remain `no-cache, no-store, must-revalidate`; content-addressed `/media/<hash>.png` remains `public, max-age=31536000, immutable`. Served `app.js` SHA-256 equals the bound source file.
- Explicit legacy on the isolated service rendered the shell for root and the three required legal deep links. Encoded unsafe/service paths, missing assets, and invalid media remained `404`.
- Browser privacy behavior used only a synthetic header-shaped fixture typed into the visible legacy textarea: it was rejected and cleared. Clipboard-read calls were `0`; the importer and request-header copy were absent. No real Cookie was entered or read, and no browser Cookie store, profile, local/session storage value, request header, environment dump, disk Cookie, or hidden state was inspected.
- The isolated legacy database SHA-256 remained `cc13ac43b47d50e6613fba435eedfe14eb279b63d6ef8dc956b0b6c37e0e7c72` before and after rollback verification.
- Temporary ports `7941` and `7942` were released, and the temporary data and Playwright directories were removed. The existing `127.0.0.1:7860` listener remained owned by PID `15948` and was not stopped or restarted.

Current machine evidence is under `output/final-closure-fix/`: `browser-smoke.json`, `batch-refresh.json`, `long-title.json`, `cache-http.json`, `legacy-http.json`, `legacy-browser.json`, `db-hash.json`, `service-cleanup.json`, both screenshot-capture maps, fresh screenshots, TDD transcripts, final verification logs, `final-evidence.json`, and the hash/size-complete `manifest.json`.

## Final seal closure 鈥?live scroll equivalence and mandatory edge markers (2026-07-12)

This seal supersedes `output/final-closure-fix/` as current proof. The wholly fresh bundle is `output/final-seal/` and is bound to production code commit `9132a8e87375bf085084210e0c76a496fbd7cb4e` and tree `c6f63159de4e5bc7883d0affa388fcc6e1e7c734`.

- The live `route/scrollSaved` reducer, direct `saveScroll()`, persistence, and restoration now share one validated recency helper. Starting with 100 routes, refreshing `/route-000`, then adding `/route-100` leaves exactly 100 live entries, evicts `/route-001`, keeps the refreshed and new routes newest, and makes live, persisted, and restored maps deeply equal in key order and values.
- Screenshot capture validation now requires `edge_marker` metadata for every screenshot. Existing coordinate, RGBA, tolerance, decoded-pixel, viewport, DPR, bottom-navigation, essential-rect, artifact-size, and SHA-256 checks remain active.
- Every one of the 14 fresh screenshots injects a fixed 1 CSS-pixel marker at the right/bottom edge immediately before the viewport screenshot and removes it immediately afterward. Capture mode is exclusively `raw-device-pixels`, with DPR `1`, `visualViewport.scale=1`, and no crop or resize. `marker-audit.json` records every decoded device-pixel coordinate and RGBA match.
- The fresh V3 browser matrix passed `10/10` route/viewport rows. Anime batches 1 and 2 were non-empty and different; Back and reload retained route, batch, all titles, and `1310px` scroll. The long-title proof remained within the `390x844` document width.
- Cache behavior, same-origin `/media/*` honesty, explicit legacy legal deep links, unsafe/service `404` exclusions, visible-input-only Cookie behavior, database immutability, temporary-service cleanup, and protected `127.0.0.1:7860` PID `15948` remained intact.
- Strict RED/GREEN transcripts for the two seal findings, focused/full unittest logs, all 23 JavaScript syntax checks, hygiene/privacy scans, capture maps, visual self-check, aggregate evidence, and the validated manifest are included in `output/final-seal/`.

## Terminal review closure 鈥?route ownership, visible Cookie truth, and hardened evidence (2026-07-12)

This closure supersedes `output/final-seal/` as current proof. The wholly fresh bundle is `output/final-terminal-fix/`, bound to production code commit `d62c20957c338ccab46b36c656926089b8a70bc8` and tree `9a8bacabe04decab78e142908092875472e21303`.

- Route ownership is now established before any fallible active-space disposal or route preparation. The active-space reference is detached before its disposer runs. New behavior tests cover a throwing disposer, a throwing prepare step, and a clear-then-throw prepare step; each restores the previous stable route, persisted state, history path, navigation state, and non-empty main view. A second navigation succeeds after a poison disposer instead of retaining the broken controller.
- The visible Cookie textarea is now the same-tab `sessionStorage` truth source on every edit and at disposal, in addition to start/resume. Clearing or replacing the visible value without starting a sync survives dispose/remount correctly; an invalid profile submission cannot revive an older value. Detached secret DOM is still cleared, and no Cookie enters public UI snapshots, database, disk, logs, or reports.
- The legacy Cookie parser now accepts only direct `name=value; name=value` Cookie pairs using Cookie-octet or controlled quoted-value grammar. Embedded `Cookie:` / `Authorization:` labels, commas, unquoted whitespace, prose, prefixed fields, and multiline input are rejected. Clipboard reads and Request Headers import remain absent.
- The evidence validator now requires the marker to be the decoded lower-right device pixel, verifies the marker's one-CSS-pixel rect reaches the visual viewport right/bottom edge, enforces `mandatory_edge_marker: true`, and enforces the declared screenshot count. Negative tests cover interior markers, count mismatch, and disabled marker contracts.
- Strict TDD evidence records the intended RED failures followed by GREEN. Focused regression passed `226` tests; both complete runs passed `625` tests; all `23` JavaScript files passed `node --check`; diff, placeholder, privacy-entry, subscription-secret, and parent-package-pollution checks passed.
- Fresh V3 ran on isolated `127.0.0.1:7961` and explicit legacy on `127.0.0.1:7962`, both with fresh data and profile-free Chrome contexts. The V3 matrix passed `10/10` rows at `1440x900` and `390x844`; all audit failure arrays were empty, main content was non-empty, responsive navigation was correct, and visible images were successful same-origin `/media/*` or non-image designed fallbacks.
- Anime changed from a non-empty batch 1 to a different non-empty batch 2. Browser Back and a full reload retained the route, batch, all nine titles, and the settled `1310px` scroll. The mobile long-title stress proof remained inside the `390x844` document width.
- All `14` screenshots use `raw-device-pixels`, DPR `1`, no crop/resize, and a mandatory one-pixel lower-right marker. This run uses marker RGBA `[29, 197, 157, 255]`; all 14 screenshot hashes are unique and none matches the prior `final-seal` screenshot set, providing machine-checkable freshness in addition to source/port/timestamp provenance.
- V3 HTML/assets remained `no-cache, no-store, must-revalidate`; registered content-addressed media remained immutable; served `app.js` matched the source SHA-256. Legacy root and legal deep links rendered the legacy shell, unsafe/service paths stayed `404`, and the isolated database hash was unchanged.
- Temporary ports and data directories were released, the temporary Playwright runtime was removed, and the protected `127.0.0.1:7860` listener remained PID `15948` throughout.

Current machine evidence: `output/final-terminal-fix/final-evidence.json`, `manifest.json`, `marker-audit.json`, `browser-smoke.json`, `batch-refresh.json`, `long-title.json`, `cache-http.json`, `legacy-http.json`, `legacy-browser.json`, `db-hash.json`, `service-cleanup.json`, screenshot capture maps, fresh screenshots, strict TDD logs, full verification logs, and `visual-self-check.jpg`.
