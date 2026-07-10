from __future__ import annotations

from urllib.parse import quote

from .models import MediaItem, normalize_title


POSTER_URLS_BY_DOUBAN_ID: dict[str, str] = {
    "27010768": "https://img1.doubanio.com/view/photo/s_ratio_poster/public/p2561439800.webp",  # 寄生虫
    "26842702": "https://img1.doubanio.com/view/photo/s_ratio_poster/public/p2520095279.webp",  # 燃烧
    "1293182": "https://img3.doubanio.com/view/photo/s_ratio_poster/public/p2173577632.webp",  # 十二怒汉
    "1296141": "https://img3.doubanio.com/view/photo/s_ratio_poster/public/p2927451337.webp",  # 控方证人
    "21937445": "https://img9.doubanio.com/view/photo/s_ratio_poster/public/p2158166535.webp",  # 辩护人
    "24733428": "https://img1.doubanio.com/view/photo/s_ratio_poster/public/p2595591069.webp",  # 心灵奇旅
    "35465232": "https://img9.doubanio.com/view/photo/s_ratio_poster/public/p2890906384.webp",  # 漫长的季节
    "33404425": "https://img1.doubanio.com/view/photo/s_ratio_poster/public/p2609064048.webp",  # 隐秘的角落
    "2373195": "https://img1.doubanio.com/view/photo/s_ratio_poster/public/p2886443948.webp",  # 绝命毒师
    "25897712": "https://img1.doubanio.com/view/photo/s_ratio_poster/public/p2218944919.webp",  # 风骚律师
    "1418192": "https://img1.doubanio.com/view/photo/s_ratio_poster/public/p926249640.webp",  # 火线 第一季
    "35350437": "https://img3.doubanio.com/view/photo/s_ratio_poster/public/p2869925687.webp",  # 我的解放日志
    "3430169": "https://img9.doubanio.com/view/photo/s_ratio_poster/public/p2225808366.webp",  # 钢之炼金术师FA
    "23748525": "https://img9.doubanio.com/view/photo/s_ratio_poster/public/p2602681134.webp",  # 进击的巨人
    "1424406": "https://img1.doubanio.com/view/photo/s_ratio_poster/public/p2011424828.webp",  # 星际牛仔
    "1460915": "https://img3.doubanio.com/view/photo/s_ratio_poster/public/p2330163082.webp",  # 混沌武士
    "1800597": "https://img3.doubanio.com/view/photo/s_ratio_poster/public/p2242716237.webp",  # 虫师
    "4925398": "https://img3.doubanio.com/view/photo/s_ratio_poster/public/p1948151693.webp",  # 命运石之门
    "26677934": "https://img3.doubanio.com/view/photo/s_ratio_poster/public/p2358698477.webp",  # 灵能百分百
    "36093351": "https://img9.doubanio.com/view/photo/s_ratio_poster/public/p2897218476.webp",  # 葬送的芙莉莲
    "35366293": "https://img9.doubanio.com/view/photo/s_ratio_poster/public/p2880400525.webp",  # 孤独摇滚！
    "35332568": "https://img3.doubanio.com/view/photo/s_ratio_poster/public/p2631090442.webp",  # 奇巧计程车
    "3060542": "https://img2.doubanio.com/view/photo/s_ratio_poster/public/p2221083211.webp",  # 夏目友人帐
    "2340927": "https://img3.doubanio.com/view/photo/s_ratio_poster/public/p1995752943.webp",  # 怪化猫
    "35633650": "https://img3.doubanio.com/view/photo/s_ratio_poster/public/p2896940977.webp",  # 坠落的审判
    "35712804": "https://img1.doubanio.com/view/photo/s_ratio_poster/public/p2904961420.webp",  # 白日之下
    "35208463": "https://img1.doubanio.com/view/photo/s_ratio_poster/public/p2901703469.webp",  # 三大队
    "35725869": "https://img1.doubanio.com/view/photo/s_ratio_poster/public/p2901057189.webp",  # 年会不能停！
    "35209683": "https://img2.doubanio.com/view/photo/s_ratio_poster/public/p2899486451.webp",  # 河边的错误
    "35206444": "https://img2.doubanio.com/view/photo/s_ratio_poster/public/p2637459961.webp",  # 模范出租车
    "30468961": "https://img2.doubanio.com/view/photo/s_ratio_poster/public/p2576977981.webp",  # 想见你
    "35881324": "https://img1.doubanio.com/view/photo/s_ratio_poster/public/p2900138920.webp",  # 以爱为营
}


POSTER_URLS_BY_DOUBAN_ID.update({
    "35674355": "https://img1.doubanio.com/view/photo/s_ratio_poster/public/p2885130077.jpg",
    "34867871": "https://img3.doubanio.com/view/photo/s_ratio_poster/public/p2714077426.webp",
    "34927946": "https://img1.doubanio.com/view/photo/s_ratio_poster/public/p2633263610.webp",
    "27624762": "https://img3.doubanio.com/view/photo/s_ratio_poster/public/p2707610653.jpg",
    "30395914": "https://img1.doubanio.com/view/photo/s_ratio_poster/public/p2615404769.jpg",
    "27121260": "https://img3.doubanio.com/view/photo/s_ratio_poster/public/p2650641487.jpg",
    "35263440": "https://img9.doubanio.com/view/photo/s_ratio_poster/public/p2669131265.jpg",
    "30424374": "https://img1.doubanio.com/view/photo/s_ratio_poster/public/p2551717438.jpg",
    "1938084": "https://img1.doubanio.com/view/photo/s_ratio_poster/public/p2873984509.jpg",
})

POSTER_URLS_BY_DOUBAN_ID.update({
    "1304447": "https://m.media-amazon.com/images/M/MV5BMGQ3Y2Q4NjktN2E4Ny00Y2Q2LTliZDUtZTNiNjRhY2I0NGIyXkEyXkFqcGc@._V1_.jpg",
    "1780330": "https://media.themoviedb.org/t/p/w500/bdN3gXuIZYaJP7ftKK2sU0nPtEA.jpg",
    "35235502": "https://m.media-amazon.com/images/M/MV5BOGE5ZWRhYjYtNzVkMS00ZGU3LTg2MTMtODYyMmJlMDMyZjU0XkEyXkFqcGc@._V1_.jpg",
    "35052676": "https://m.media-amazon.com/images/M/MV5BNWYyMDkxY2ItNmRmMC00Y2ZmLTkwZGYtNDJiYmZhOGUzOGY0XkEyXkFqcGc@._V1_.jpg",
    "10539853": "https://static.tvmaze.com/uploads/images/original_untouched/7/17646.jpg",
    "30238385": "https://static.tvmaze.com/uploads/images/original_untouched/501/1253559.jpg",
})


PEOPLE_PHOTOS_BY_DOUBAN_ID: dict[str, dict[str, str]] = {
    "27010768": {  # 寄生虫
        "奉俊昊": "https://upload.wikimedia.org/wikipedia/commons/thumb/f/fb/Bong_Joon-ho_2017.jpg/330px-Bong_Joon-ho_2017.jpg",
        "宋康昊": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/df/Song_Gangho_2016.jpg/330px-Song_Gangho_2016.jpg",
        "李善均": "https://upload.wikimedia.org/wikipedia/commons/thumb/6/6f/Lee_Seon-gun_in_Oct_2018.png/330px-Lee_Seon-gun_in_Oct_2018.png",
    },
    "1296141": {  # 控方证人
        "比利·怀尔德": "https://upload.wikimedia.org/wikipedia/commons/d/d0/Billy_Wilder.jpg",
        "泰隆·鲍华": "https://upload.wikimedia.org/wikipedia/commons/thumb/7/73/Tyrone_Power_-_still.jpg/330px-Tyrone_Power_-_still.jpg",
        "玛琳·黛德丽": "https://upload.wikimedia.org/wikipedia/commons/thumb/2/2d/Marlene_Dietrich_in_No_Highway_%281951%29_%28Cropped%29.png/330px-Marlene_Dietrich_in_No_Highway_%281951%29_%28Cropped%29.png",
    },
    "1418192": {  # 火线 第一季
        "克拉克·约翰森": "https://upload.wikimedia.org/wikipedia/commons/thumb/1/1c/Clark_Johnson.jpg/330px-Clark_Johnson.jpg",
        "多米尼克·韦斯特": "https://upload.wikimedia.org/wikipedia/commons/thumb/5/5a/Dominic_West_%286577113511%29_%28cropped%29.jpg/330px-Dominic_West_%286577113511%29_%28cropped%29.jpg",
        "约翰·道曼": "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b2/John_Doman_2013_%28cropped_2%29.jpg/330px-John_Doman_2013_%28cropped_2%29.jpg",
    },
    "2373195": {  # 绝命毒师
        "文斯·吉里根": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/3d/Vince_Gilligan_at_53rd_Saturn_Awards_2026-03.jpg/330px-Vince_Gilligan_at_53rd_Saturn_Awards_2026-03.jpg",
        "布莱恩·克兰斯顿": "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b1/BryanCranston-byPhilipRomano.jpg/330px-BryanCranston-byPhilipRomano.jpg",
        "亚伦·保尔": "https://upload.wikimedia.org/wikipedia/commons/thumb/9/9a/Aaron_Paul_-_AMC_The_Grove_-_Ash.jpg/330px-Aaron_Paul_-_AMC_The_Grove_-_Ash.jpg",
    },
    "25897712": {  # 风骚律师
        "文斯·吉里根": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/3d/Vince_Gilligan_at_53rd_Saturn_Awards_2026-03.jpg/330px-Vince_Gilligan_at_53rd_Saturn_Awards_2026-03.jpg",
        "鲍勃·奥登科克": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/84/Bob_Odenkirk_at_53rd_Saturn_Awards_2026-02.jpg/330px-Bob_Odenkirk_at_53rd_Saturn_Awards_2026-02.jpg",
    },
    "33404425": {  # 隐秘的角落
        "辛爽": "https://p1-tt.byteimg.com/origin/tos-cn-i-qvj2lq49k0/35423efd92cc4580a817f2021d67e6ff.jpg",
        "秦昊": "https://i.mydramalist.com/pr8qE_5_c.jpg",
        "王景春": "https://media.gettyimages.com/id/1186966482/photo/san-sebastian-spain-chinese-actor-wang-jingchun-poses-during-a-portrait-session-at-maria.jpg?s=612x612&w=gi&k=20&c=qZvKvwZTEbUyk6IEPxqbQSc55U0dj3S-6BrZPfuOZnc=",
        "荣梓杉": "https://media.gettyimages.com/id/1311831746/photo/shanghai-china-actor-rong-zishan-attends-2021-signs-of-the-times-awards-on-april-10-2021-in.jpg?s=612x612&w=gi&k=20&c=laMzh9nfS8ICovqcfrWshbWjA5E3avQtrMBQ72ix3Xg=",
    },
    "35465232": {  # 漫长的季节
        "辛爽": "https://p1-tt.byteimg.com/origin/tos-cn-i-qvj2lq49k0/35423efd92cc4580a817f2021d67e6ff.jpg",
        "秦昊": "https://i.mydramalist.com/pr8qE_5_c.jpg",
    },
    "35633650": {  # 坠落的审判
        "茹斯汀·特里耶": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/ce/AnatomyOfFallPicCent011123_%281_of_8%29_%2853327939769%29_%28cropped%29.jpg/330px-AnatomyOfFallPicCent011123_%281_of_8%29_%2853327939769%29_%28cropped%29.jpg",
        "桑德拉·惠勒": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c3/Sandra_H%C3%BCller_at_Berlinale_2026-6.jpg/330px-Sandra_H%C3%BCller_at_Berlinale_2026-6.jpg",
    },
    "35366293": {  # 孤独摇滚！
        "斋藤圭一郎": "https://media.themoviedb.org/t/p/w500/zlRQwhbblqGQudJV4CDycOVJSDH.jpg",
        "青山吉能": "https://cdn.umamusu.wiki/Yoshino_Aoyama_Portrait.jpg",
    },
}


POSTER_URLS_BY_DOUBAN_ID.update({
    "35674355": "https://img1.doubanio.com/view/photo/s_ratio_poster/public/p2885130077.jpg",
    "34867871": "https://img3.doubanio.com/view/photo/s_ratio_poster/public/p2714077426.webp",
    "34927946": "https://img1.doubanio.com/view/photo/s_ratio_poster/public/p2633263610.webp",
    "27624762": "https://img3.doubanio.com/view/photo/s_ratio_poster/public/p2707610653.jpg",
    "30395914": "https://img1.doubanio.com/view/photo/s_ratio_poster/public/p2615404769.jpg",
    "27121260": "https://img3.doubanio.com/view/photo/s_ratio_poster/public/p2650641487.jpg",
    "35263440": "https://img9.doubanio.com/view/photo/s_ratio_poster/public/p2669131265.jpg",
    "30424374": "https://img1.doubanio.com/view/photo/s_ratio_poster/public/p2551717438.jpg",
    "1938084": "https://img1.doubanio.com/view/photo/s_ratio_poster/public/p2873984509.jpg",
})


PEOPLE_PHOTOS_BY_DOUBAN_ID.update({
    "25895901": {
        "是枝裕和": "https://upload.wikimedia.org/wikipedia/commons/8/8c/Hirokazu_Kore-eda_Cannes_2015.jpg",
        "绫濑遥": "https://upload.wikimedia.org/wikipedia/commons/6/6f/Haruka_Ayase_%28cropped%29.jpg",
        "长泽雅美": "https://upload.wikimedia.org/wikipedia/commons/8/81/Masami_Nagasawa_%40_Japan_Cuts_2012_-_10.jpg",
        "夏帆": "https://upload.wikimedia.org/wikipedia/commons/a/ac/Kaho_Cannes_2015.jpg",
        "广濑铃": "https://upload.wikimedia.org/wikipedia/commons/9/95/Suzu_Hirose_Cannes_2015.jpg",
        "广濑丝丝": "https://upload.wikimedia.org/wikipedia/commons/9/95/Suzu_Hirose_Cannes_2015.jpg",
    },
    "30166972": {
        "曾国祥": "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e8/Derektsang2010.jpg/330px-Derektsang2010.jpg",
        "周冬雨": "https://upload.wikimedia.org/wikipedia/commons/thumb/5/55/%E5%91%A8%E5%86%AC%E9%9B%A8_-_2017%E5%BE%AE%E5%8D%9A%E7%94%B5%E5%BD%B1%E4%B9%8B%E5%A4%9C%283%29_-_cropped.jpg/330px-%E5%91%A8%E5%86%AC%E9%9B%A8_-_2017%E5%BE%AE%E5%8D%9A%E7%94%B5%E5%BD%B1%E4%B9%8B%E5%A4%9C%283%29_-_cropped.jpg",
        "易烊千玺": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a4/%E6%98%93%E7%83%8A%E5%8D%83%E7%8E%BA_Jackson_Yee.jpg/330px-%E6%98%93%E7%83%8A%E5%8D%83%E7%8E%BA_Jackson_Yee.jpg",
        "尹昉": "https://metadata-static.plex.tv/people/5d776d96ad5437001f7c1e14.jpg",
        "周也": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/39/Zhou_Ye_at_Weibo_Night_2023.jpg/330px-Zhou_Ye_at_Weibo_Night_2023.jpg",
    },
})


PEOPLE_PHOTOS_BY_DOUBAN_ID.update({
    "1293182": {
        "\u897f\u5fb7\u5c3c\u00b7\u5415\u7f8e\u7279": "https://upload.wikimedia.org/wikipedia/commons/thumb/6/6a/Sidney_Lumet_2007.jpg/330px-Sidney_Lumet_2007.jpg",
        "\u4ea8\u5229\u00b7\u65b9\u8fbe": "https://upload.wikimedia.org/wikipedia/commons/thumb/2/2d/Henry_Fonda_NYWTS.jpg/330px-Henry_Fonda_NYWTS.jpg",
        "\u9a6c\u4e01\u00b7\u9c8d\u5c14\u8428\u59c6": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/8c/Martin_Balsam_1960.JPG/330px-Martin_Balsam_1960.JPG",
    },
    "21937445": {
        "\u5b8b\u5eb7\u660a": PEOPLE_PHOTOS_BY_DOUBAN_ID["27010768"]["\u5b8b\u5eb7\u660a"],
    },
    "35206444": {
        "\u674e\u5e1d\u52cb": "https://i.mydramalist.com/2wZ2O_5_c.jpg",
        "\u674e\u7d6e": "https://i.mydramalist.com/1wz2K_5_c.jpg",
        "\u91d1\u4e49\u57ce": "https://i.mydramalist.com/0kL0O_5_c.jpg",
    },
})


PEOPLE_PHOTOS_BY_DOUBAN_ID.update({
    "1304447": {
        "????????": "https://m.media-amazon.com/images/M/MV5BNjE3NDQyOTYyMV5BMl5BanBnXkFtZTcwODcyODU2Mw@@._V1_.jpg",
        "?????": "https://m.media-amazon.com/images/M/MV5BMTgyNzc2NzY3Nl5BMl5BanBnXkFtZTgwNTMzMzAwMjE@._V1_.jpg",
        "??-????": "https://m.media-amazon.com/images/M/MV5BMTYxMjgwNzEwOF5BMl5BanBnXkFtZTcwNTQ0NzI5Ng@@._V1_.jpg",
    },
    "35235502": {
        "????": "https://m.media-amazon.com/images/M/MV5BNWI5MmVkYjUtYzNjMC00NGMyLWIyMjctOGJiY2YwZDRkYjc5XkEyXkFqcGc@._V1_.jpg",
        "????": "https://m.media-amazon.com/images/M/MV5BMjVhNjM4NTAtMjY4My00NzFiLWFjOTItMjUxOWVkYjBhMGVlXkEyXkFqcGc@._V1_.jpg",
        "????": "https://m.media-amazon.com/images/M/MV5BYTRiODJkMmQtZGYwNC00OWY5LWIxZGMtMGJlYTdjOTNlOWQ0XkEyXkFqcGc@._V1_.jpg",
    },
    "35052676": {
        "???": "https://m.media-amazon.com/images/M/MV5BMmI3Y2YwODAtMTliZi00NTlmLTk5ODQtMmUyYjQwNGE1MWQzXkEyXkFqcGc@._V1_.jpg",
        "???": "https://m.media-amazon.com/images/M/MV5BMTcxMjE0MDI3NV5BMl5BanBnXkFtZTgwMTkzMjEyMjE@._V1_.jpg",
        "???": "https://m.media-amazon.com/images/M/MV5BN2MyZmVlNzAtOGYwOS00YTdiLTgyNDYtMWVhNGQ5YjgwMzdhXkEyXkFqcGc@._V1_.jpg",
    },
    "10539853": {
        "?????????": "https://m.media-amazon.com/images/M/MV5BMjU3MWI2NjAtOTBhZi00OGVhLWIxYmItNTU3YzlkMmZkZTY0XkEyXkFqcGc@._V1_.jpg",
        "???????": "https://m.media-amazon.com/images/M/MV5BY2NjYjA4MjAtYTM0Ni00OGM4LWEyNzQtNGUxODhiZTNlNjA2XkEyXkFqcGc@._V1_.jpg",
        "?????": "https://m.media-amazon.com/images/M/MV5BZjhhYWNiN2MtNmVkZS00ZTAyLThjNTEtYjQ4MDMwODQ4YmQ5XkEyXkFqcGc@._V1_.jpg",
        "????????": "https://m.media-amazon.com/images/M/MV5BMGJjODI2MTUtNmMwOS00YjM3LWIzMDUtMWI4MmE0OWM2M2VlXkEyXkFqcGc@._V1_.jpg",
    },
    "30238385": {
        "?????": "https://m.media-amazon.com/images/M/MV5BMTk4NjMyNzY3MV5BMl5BanBnXkFtZTgwNDY0Nzg0ODE@._V1_.jpg",
        "?????": "https://m.media-amazon.com/images/M/MV5BMTc1NDkwMTQ2MF5BMl5BanBnXkFtZTcwMzY0ODkyMg@@._V1_.jpg",
    },
})

TITLE_PEOPLE_METADATA: dict[str, dict[str, object]] = {
    "????": {
        "douban_id": "1304447",
        "year": 2000,
        "directors": ["????????"],
        "casts": ["?????", "??-????"],
        "people_photos": PEOPLE_PHOTOS_BY_DOUBAN_ID["1304447"],
    },
    "?????": {
        "douban_id": "35235502",
        "year": 2021,
        "directors": ["????"],
        "casts": ["????", "????"],
        "people_photos": PEOPLE_PHOTOS_BY_DOUBAN_ID["35235502"],
    },
    "????": {
        "douban_id": "35052676",
        "year": 2021,
        "directors": ["???"],
        "casts": ["???", "???"],
        "people_photos": PEOPLE_PHOTOS_BY_DOUBAN_ID["35052676"],
    },
    "?????": {
        "douban_id": "10539853",
        "year": 2013,
        "directors": ["?????????"],
        "casts": ["???????", "?????", "????????"],
        "people_photos": PEOPLE_PHOTOS_BY_DOUBAN_ID["10539853"],
    },
    "????????": {
        "douban_id": "30238385",
        "year": 2019,
        "directors": ["?????", "?????"],
        "casts": ["??????"],
        "people_photos": PEOPLE_PHOTOS_BY_DOUBAN_ID["30238385"],
    },
    "海街日记": {
        "douban_id": "25895901",
        "year": 2015,
        "directors": ["是枝裕和"],
        "casts": ["绫濑遥", "长泽雅美", "夏帆", "广濑铃"],
        "people_photos": PEOPLE_PHOTOS_BY_DOUBAN_ID["25895901"],
    },
    "少年的你": {
        "douban_id": "30166972",
        "year": 2019,
        "directors": ["曾国祥"],
        "casts": ["周冬雨", "易烊千玺", "尹昉", "周也"],
        "people_photos": PEOPLE_PHOTOS_BY_DOUBAN_ID["30166972"],
    },
}

PEOPLE_PHOTOS_BY_DOUBAN_ID.update({
    "1304447": {
        "克里斯托弗·诺兰": "https://m.media-amazon.com/images/M/MV5BNjE3NDQyOTYyMV5BMl5BanBnXkFtZTcwODcyODU2Mw@@._V1_.jpg",
        "盖·皮尔斯": "https://m.media-amazon.com/images/M/MV5BMTgyNzc2NzY3Nl5BMl5BanBnXkFtZTgwNTMzMzAwMjE@._V1_.jpg",
        "凯瑞-安·莫斯": "https://m.media-amazon.com/images/M/MV5BMTYxMjgwNzEwOF5BMl5BanBnXkFtZTcwNTQ0NzI5Ng@@._V1_.jpg",
    },
    "35235502": {
        "滨口龙介": "https://m.media-amazon.com/images/M/MV5BNWI5MmVkYjUtYzNjMC00NGMyLWIyMjctOGJiY2YwZDRkYjc5XkEyXkFqcGc@._V1_.jpg",
        "西岛秀俊": "https://m.media-amazon.com/images/M/MV5BMjVhNjM4NTAtMjY4My00NzFiLWFjOTItMjUxOWVkYjBhMGVlXkEyXkFqcGc@._V1_.jpg",
        "三浦透子": "https://m.media-amazon.com/images/M/MV5BYTRiODJkMmQtZGYwNC00OWY5LWIxZGMtMGJlYTdjOTNlOWQ0XkEyXkFqcGc@._V1_.jpg",
    },
    "35052676": {
        "李濬益": "https://m.media-amazon.com/images/M/MV5BMmI3Y2YwODAtMTliZi00NTlmLTk5ODQtMmUyYjQwNGE1MWQzXkEyXkFqcGc@._V1_.jpg",
        "薛景求": "https://m.media-amazon.com/images/M/MV5BMTcxMjE0MDI3NV5BMl5BanBnXkFtZTgwMTkzMjEyMjE@._V1_.jpg",
        "卞约汉": "https://m.media-amazon.com/images/M/MV5BN2MyZmVlNzAtOGYwOS00YTdiLTgyNDYtMWVhNGQ5YjgwMzdhXkEyXkFqcGc@._V1_.jpg",
    },
    "10539853": {
        "菲利普·卡德尔巴赫": "https://m.media-amazon.com/images/M/MV5BMjU3MWI2NjAtOTBhZi00OGVhLWIxYmItNTU3YzlkMmZkZTY0XkEyXkFqcGc@._V1_.jpg",
        "沃尔克·布鲁赫": "https://m.media-amazon.com/images/M/MV5BY2NjYjA4MjAtYTM0Ni00OGM4LWEyNzQtNGUxODhiZTNlNjA2XkEyXkFqcGc@._V1_.jpg",
        "汤姆·希林": "https://m.media-amazon.com/images/M/MV5BZjhhYWNiN2MtNmVkZS00ZTAyLThjNTEtYjQ4MDMwODQ4YmQ5XkEyXkFqcGc@._V1_.jpg",
        "卡塔琳娜·舒特勒": "https://m.media-amazon.com/images/M/MV5BMGJjODI2MTUtNmMwOS00YjM3LWIzMDUtMWI4MmE0OWM2M2VlXkEyXkFqcGc@._V1_.jpg",
    },
    "30238385": {
        "蒂姆·米勒": "https://m.media-amazon.com/images/M/MV5BMTk4NjMyNzY3MV5BMl5BanBnXkFtZTgwNDY0Nzg0ODE@._V1_.jpg",
        "大卫·芬奇": "https://m.media-amazon.com/images/M/MV5BMTc1NDkwMTQ2MF5BMl5BanBnXkFtZTcwMzY0ODkyMg@@._V1_.jpg",
    },
})

PEOPLE_PHOTOS_BY_DOUBAN_ID.update({
    "1780330": {
        "克里斯托弗·诺兰": "https://upload.wikimedia.org/wikipedia/commons/thumb/9/95/Christopher_Nolan_Cannes_2018.jpg/330px-Christopher_Nolan_Cannes_2018.jpg",
        "休·杰克曼": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/02/Hugh_Jackman_by_Gage_Skidmore_3.jpg/330px-Hugh_Jackman_by_Gage_Skidmore_3.jpg",
        "克里斯蒂安·贝尔": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/0a/Christian_Bale-7837.jpg/330px-Christian_Bale-7837.jpg",
        "迈克尔·凯恩": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/3d/Michael_Caine_-_Viennale_2012_g_%28cropped%29.jpg/330px-Michael_Caine_-_Viennale_2012_g_%28cropped%29.jpg",
    },
    "26842702": {
        "李沧东": "https://upload.wikimedia.org/wikipedia/commons/thumb/f/fc/Lee_Chang-dong_2010.jpg/330px-Lee_Chang-dong_2010.jpg",
        "刘亚仁": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/00/Yoo_Ah-In_%EC%9C%A0%EC%95%84%EC%9D%B8_20181206.jpg/330px-Yoo_Ah-In_%EC%9C%A0%EC%95%84%EC%9D%B8_20181206.jpg",
        "史蒂文·元": "https://upload.wikimedia.org/wikipedia/commons/thumb/7/76/Steven_Yeun_at_the_2025_Sundance_Film_Festival_%28cropped%29.jpg/330px-Steven_Yeun_at_the_2025_Sundance_Film_Festival_%28cropped%29.jpg",
        "全钟瑞": "https://upload.wikimedia.org/wikipedia/commons/thumb/b/bd/Jeon_Jong-seo_in_May_2025.png/330px-Jeon_Jong-seo_in_May_2025.png",
    },
})

TITLE_PEOPLE_METADATA.update({
    "记忆碎片": {
        "douban_id": "1304447",
        "year": 2000,
        "directors": ["克里斯托弗·诺兰"],
        "casts": ["盖·皮尔斯", "凯瑞-安·莫斯"],
        "people_photos": PEOPLE_PHOTOS_BY_DOUBAN_ID["1304447"],
    },
    "致命魔术": {
        "douban_id": "1780330",
        "year": 2006,
        "genres": ["剧情", "悬疑", "惊悚"],
        "countries": ["美国", "英国"],
        "directors": ["克里斯托弗·诺兰"],
        "casts": ["休·杰克曼", "克里斯蒂安·贝尔", "迈克尔·凯恩"],
        "people_photos": PEOPLE_PHOTOS_BY_DOUBAN_ID["1780330"],
    },
    "燃烧": {
        "douban_id": "26842702",
        "year": 2018,
        "genres": ["剧情", "悬疑"],
        "countries": ["韩国"],
        "directors": ["李沧东"],
        "casts": ["刘亚仁", "史蒂文·元", "全钟瑞"],
        "people_photos": PEOPLE_PHOTOS_BY_DOUBAN_ID["26842702"],
    },
    "驾驶我的车": {
        "douban_id": "35235502",
        "year": 2021,
        "directors": ["滨口龙介"],
        "casts": ["西岛秀俊", "三浦透子"],
        "people_photos": PEOPLE_PHOTOS_BY_DOUBAN_ID["35235502"],
    },
    "兹山鱼谱": {
        "douban_id": "35052676",
        "year": 2021,
        "directors": ["李濬益"],
        "casts": ["薛景求", "卞约汉"],
        "people_photos": PEOPLE_PHOTOS_BY_DOUBAN_ID["35052676"],
    },
    "我们的父辈": {
        "douban_id": "10539853",
        "year": 2013,
        "directors": ["菲利普·卡德尔巴赫"],
        "casts": ["沃尔克·布鲁赫", "汤姆·希林", "卡塔琳娜·舒特勒"],
        "people_photos": PEOPLE_PHOTOS_BY_DOUBAN_ID["10539853"],
    },
    "爱，死亡和机器人": {
        "douban_id": "30238385",
        "year": 2019,
        "directors": ["蒂姆·米勒", "大卫·芬奇"],
        "casts": ["成人动画短篇群像"],
        "people_photos": PEOPLE_PHOTOS_BY_DOUBAN_ID["30238385"],
    },
})


# High-visibility premium rows that often appear near the top of large local
# recommendation runs. Keep these as explicit metadata instead of showing
# generic placeholder identities in the detail drawer.
PEOPLE_PHOTOS_BY_DOUBAN_ID.update({
    "1291879": {
        "黑泽明": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/48/Akirakurosawa-onthesetof7samurai-1953-page88.jpg/330px-Akirakurosawa-onthesetof7samurai-1953-page88.jpg",
        "三船敏郎": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ad/Toshiro_Mifune_1954_Scan10003_160913.jpg/330px-Toshiro_Mifune_1954_Scan10003_160913.jpg",
        "志村乔": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d6/Shimura_Takashi.JPG/330px-Shimura_Takashi.JPG",
    },
    "1295399": {
        "黑泽明": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/48/Akirakurosawa-onthesetof7samurai-1953-page88.jpg/330px-Akirakurosawa-onthesetof7samurai-1953-page88.jpg",
        "三船敏郎": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ad/Toshiro_Mifune_1954_Scan10003_160913.jpg/330px-Toshiro_Mifune_1954_Scan10003_160913.jpg",
        "志村乔": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d6/Shimura_Takashi.JPG/330px-Shimura_Takashi.JPG",
    },
    "1291818": {
        "李安": "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e2/2016_NAB_Show%27s_The_Future_of_Cinema_Conference%2C_produced_in_partnership_with_SMPTE_%2826717112630%29_%28cropped%29.jpg/330px-2016_NAB_Show%27s_The_Future_of_Cinema_Conference%2C_produced_in_partnership_with_SMPTE_%2826717112630%29_%28cropped%29.jpg",
        "郎雄": "https://upload.wikimedia.org/wikipedia/commons/2/23/%E7%AC%AC28%E5%B1%86%E9%87%91%E9%A6%AC%E5%BD%B1%E5%B8%9D%E9%83%8E%E9%9B%84.jpg",
        "杨贵媚": "https://upload.wikimedia.org/wikipedia/commons/2/22/Yang_Kuei-mei_20200303.jpg",
    },
    "26310143": {
        "金元锡": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a7/Kim_Won-seok_2025.jpg/330px-Kim_Won-seok_2025.jpg",
        "李帝勋": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/34/Lee_Je-hoon_in_November_2025.png/330px-Lee_Je-hoon_in_November_2025.png",
        "金惠秀": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c1/Kim_Hye-soo_in_March_2025.png/330px-Kim_Hye-soo_in_March_2025.png",
    },
    "34943015": {
        "申元浩": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Shin_Won-ho_%EC%8B%A0%EC%9B%90%ED%98%B8.png/330px-Shin_Won-ho_%EC%8B%A0%EC%9B%90%ED%98%B8.png",
        "曹政奚": "https://upload.wikimedia.org/wikipedia/commons/thumb/2/24/Jo_Jung-suk_in_June_2026.png/330px-Jo_Jung-suk_in_June_2026.png",
        "柳演锡": "https://upload.wikimedia.org/wikipedia/commons/thumb/6/6b/Yoo_Yeon-seok_-_Bean_Pole_catalogue_2015_Spring-Summer_02_%28cropped%29.jpg/330px-Yoo_Yeon-seok_-_Bean_Pole_catalogue_2015_Spring-Summer_02_%28cropped%29.jpg",
    },
    "cinescope-good-wife": {
        "米歇尔·金": "https://upload.wikimedia.org/wikipedia/commons/thumb/f/f8/Robert_King_and_Michelle_King_at_2015_PaleyFest.jpg/330px-Robert_King_and_Michelle_King_at_2015_PaleyFest.jpg",
        "罗伯特·金": "https://upload.wikimedia.org/wikipedia/commons/thumb/f/f8/Robert_King_and_Michelle_King_at_2015_PaleyFest.jpg/330px-Robert_King_and_Michelle_King_at_2015_PaleyFest.jpg",
        "朱丽安娜·玛格丽丝": "https://upload.wikimedia.org/wikipedia/commons/thumb/5/56/JuliannaMargulies-byPhilipRomano.jpg/330px-JuliannaMargulies-byPhilipRomano.jpg",
    },
    "cinescope-fargo": {
        "诺亚·霍利": "https://upload.wikimedia.org/wikipedia/commons/thumb/1/13/Noah_Hawley_by_Gage_Skidmore_2.jpg/330px-Noah_Hawley_by_Gage_Skidmore_2.jpg",
        "马丁·弗瑞曼": "https://upload.wikimedia.org/wikipedia/commons/thumb/7/7f/Martin_Freeman-5341.jpg/330px-Martin_Freeman-5341.jpg",
        "比利·鲍伯·松顿": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/00/Billy_Bob_Thornton_2017_%28cropped%29.jpg/330px-Billy_Bob_Thornton_2017_%28cropped%29.jpg",
    },
    "cinescope-true-detective": {
        "尼克·皮佐拉托": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/30/Nic_Pizzolatto_at_TIFF_2025_02.jpg/330px-Nic_Pizzolatto_at_TIFF_2025_02.jpg",
        "马修·麦康纳": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/8c/Matthew_McConaughey_at_the_2025_Toronto_Film_Festival_%28Cropped%29.jpg/330px-Matthew_McConaughey_at_the_2025_Toronto_Film_Festival_%28Cropped%29.jpg",
        "伍迪·哈里森": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/3a/Woody_Harrelson_191020-N-NU281-1028_%28cropped%29.jpg/330px-Woody_Harrelson_191020-N-NU281-1028_%28cropped%29.jpg",
    },
})

TITLE_PEOPLE_METADATA.update({
    "罗生门": {
        "douban_id": "1291879",
        "year": 1950,
        "genres": ["剧情", "悬疑", "犯罪"],
        "countries": ["日本"],
        "directors": ["黑泽明"],
        "casts": ["三船敏郎", "京町子", "志村乔"],
        "cover": "https://upload.wikimedia.org/wikipedia/commons/thumb/6/61/Rashomon_poster.jpg/330px-Rashomon_poster.jpg",
        "people_photos": PEOPLE_PHOTOS_BY_DOUBAN_ID["1291879"],
    },
    "七武士": {
        "douban_id": "1295399",
        "year": 1954,
        "genres": ["剧情", "动作", "冒险"],
        "countries": ["日本"],
        "directors": ["黑泽明"],
        "casts": ["三船敏郎", "志村乔"],
        "cover": "https://upload.wikimedia.org/wikipedia/en/c/c8/Seven_Samurai_Poster.png",
        "people_photos": PEOPLE_PHOTOS_BY_DOUBAN_ID["1295399"],
    },
    "饮食男女": {
        "douban_id": "1291818",
        "year": 1994,
        "genres": ["剧情", "家庭"],
        "countries": ["中国台湾", "美国"],
        "directors": ["李安"],
        "casts": ["郎雄", "杨贵媚", "吴倩莲"],
        "cover": "https://upload.wikimedia.org/wikipedia/en/b/b4/Eat_Drink_Man_Woman.jpg",
        "people_photos": PEOPLE_PHOTOS_BY_DOUBAN_ID["1291818"],
    },
    "信号": {
        "douban_id": "26310143",
        "year": 2016,
        "genres": ["剧情", "悬疑", "犯罪"],
        "countries": ["韩国"],
        "directors": ["金元锡"],
        "casts": ["李帝勋", "金惠秀", "赵震雄"],
        "cover": "https://static.tvmaze.com/uploads/images/original_untouched/139/349655.jpg",
        "people_photos": PEOPLE_PHOTOS_BY_DOUBAN_ID["26310143"],
    },
    "机智医生生活": {
        "douban_id": "34943015",
        "year": 2020,
        "genres": ["剧情", "喜剧"],
        "countries": ["韩国"],
        "directors": ["申元浩"],
        "casts": ["曹政奚", "柳演锡", "郑敬淘"],
        "cover": "https://static.tvmaze.com/uploads/images/original_untouched/323/807792.jpg",
        "people_photos": PEOPLE_PHOTOS_BY_DOUBAN_ID["34943015"],
    },
    "傲骨贤妻": {
        "year": 2009,
        "genres": ["剧情", "悬疑", "犯罪"],
        "countries": ["美国"],
        "directors": ["米歇尔·金", "罗伯特·金"],
        "casts": ["朱丽安娜·玛格丽丝", "克里斯·诺斯"],
        "cover": "https://static.tvmaze.com/uploads/images/original_untouched/59/148162.jpg",
        "people_photos": PEOPLE_PHOTOS_BY_DOUBAN_ID["cinescope-good-wife"],
    },
    "冰血暴": {
        "year": 2014,
        "genres": ["剧情", "犯罪", "惊悚"],
        "countries": ["美国"],
        "directors": ["诺亚·霍利"],
        "casts": ["马丁·弗瑞曼", "比利·鲍伯·松顿"],
        "cover": "https://static.tvmaze.com/uploads/images/original_untouched/487/1219631.jpg",
        "people_photos": PEOPLE_PHOTOS_BY_DOUBAN_ID["cinescope-fargo"],
    },
    "真探": {
        "year": 2014,
        "genres": ["剧情", "悬疑", "犯罪"],
        "countries": ["美国"],
        "directors": ["尼克·皮佐拉托"],
        "casts": ["马修·麦康纳", "伍迪·哈里森"],
        "cover": "https://static.tvmaze.com/uploads/images/original_untouched/490/1226764.jpg",
        "people_photos": PEOPLE_PHOTOS_BY_DOUBAN_ID["cinescope-true-detective"],
    },
})

PEOPLE_PHOTOS_BY_DOUBAN_ID.update({
    "34867871": {
        "克里斯蒂安·林克": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/8a/Hailee_Steinfeld_by_Gage_Skidmore.jpg/330px-Hailee_Steinfeld_by_Gage_Skidmore.jpg",
        "海莉·斯坦菲尔德": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/8a/Hailee_Steinfeld_by_Gage_Skidmore.jpg/330px-Hailee_Steinfeld_by_Gage_Skidmore.jpg",
        "艾拉·普尔内尔": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4c/Ella_Purnell_at_MEGACON_Orlando_2025.png/330px-Ella_Purnell_at_MEGACON_Orlando_2025.png",
    },
    "34927946": {
        "罗伯特·柯克曼": "https://upload.wikimedia.org/wikipedia/commons/thumb/7/7b/Robert_Kirkman_by_Gage_Skidmore_5.jpg/330px-Robert_Kirkman_by_Gage_Skidmore_5.jpg",
        "史蒂文·元": "https://upload.wikimedia.org/wikipedia/commons/thumb/7/76/Steven_Yeun_at_the_2025_Sundance_Film_Festival_%28cropped%29.jpg/330px-Steven_Yeun_at_the_2025_Sundance_Film_Festival_%28cropped%29.jpg",
        "J.K.西蒙斯": "https://upload.wikimedia.org/wikipedia/commons/thumb/5/5b/JK_Simmons_at_the_2024_Toronto_International_Film_Festival_%28cropped%29.jpg/330px-JK_Simmons_at_the_2024_Toronto_International_Film_Festival_%28cropped%29.jpg",
    },
    "1938084": {
        "迈克尔·丹特·迪马蒂诺": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ae/Michael_Dante_DiMartino_by_Gage_Skidmore_2.jpg/330px-Michael_Dante_DiMartino_by_Gage_Skidmore_2.jpg",
        "布莱恩·科尼茨科": "https://upload.wikimedia.org/wikipedia/commons/thumb/5/53/Bryan_Konietzko_by_Gage_Skidmore_2.jpg/330px-Bryan_Konietzko_by_Gage_Skidmore_2.jpg",
        "扎克·泰勒": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a2/Zack_Tyler_Eisen_at_Animate%21_Raleigh_%2855168634758%29.jpg/330px-Zack_Tyler_Eisen_at_Animate%21_Raleigh_%2855168634758%29.jpg",
    },
})

PEOPLE_PHOTOS_BY_DOUBAN_ID.update({
    "1424406": {  # 星际牛仔
        "渡边信一郎": "https://cdn.myanimelist.net/images/voiceactors/3/48770.jpg",
        "山寺宏一": "https://cdn.myanimelist.net/images/voiceactors/2/73614.jpg",
        "石冢运升": "https://cdn.myanimelist.net/images/voiceactors/2/17135.jpg",
        "林原惠美": "https://cdn.myanimelist.net/images/voiceactors/3/63419.jpg",
    },
    "1460915": {  # 混沌武士
        "渡边信一郎": "https://cdn.myanimelist.net/images/voiceactors/3/48770.jpg",
        "中井和哉": "https://cdn.myanimelist.net/images/voiceactors/1/62866.jpg",
        "川澄绫子": "https://cdn.myanimelist.net/images/voiceactors/2/69419.jpg",
        "佐藤银平": "https://cdn.myanimelist.net/images/voiceactors/3/16427.jpg",
    },
    "1800597": {  # 虫师
        "长滨博史": "https://cdn.myanimelist.net/images/voiceactors/2/40470.jpg",
        "中野裕斗": "https://cdn.myanimelist.net/images/voiceactors/2/80247.jpg",
        "土井美加": "https://cdn.myanimelist.net/images/voiceactors/3/90070.jpg",
    },
})

TITLE_PEOPLE_METADATA.update({
    "星际牛仔": {
        "douban_id": "1424406",
        "year": 1998,
        "genres": ["动画", "剧情", "科幻"],
        "countries": ["日本"],
        "directors": ["渡边信一郎"],
        "casts": ["山寺宏一", "石冢运升", "林原惠美"],
        "people_photos": PEOPLE_PHOTOS_BY_DOUBAN_ID["1424406"],
    },
    "混沌武士": {
        "douban_id": "1460915",
        "year": 2004,
        "genres": ["动画", "动作", "冒险"],
        "countries": ["日本"],
        "directors": ["渡边信一郎"],
        "casts": ["中井和哉", "川澄绫子", "佐藤银平"],
        "people_photos": PEOPLE_PHOTOS_BY_DOUBAN_ID["1460915"],
    },
    "虫师": {
        "douban_id": "1800597",
        "year": 2005,
        "genres": ["动画", "剧情", "奇幻"],
        "countries": ["日本"],
        "directors": ["长滨博史"],
        "casts": ["中野裕斗", "土井美加"],
        "people_photos": PEOPLE_PHOTOS_BY_DOUBAN_ID["1800597"],
    },
    "英雄联盟：双城之战": {
        "douban_id": "34867871",
        "year": 2021,
        "genres": ["动画", "剧情", "动作"],
        "countries": ["美国", "法国"],
        "directors": ["克里斯蒂安·林克"],
        "casts": ["海莉·斯坦菲尔德", "艾拉·普尔内尔"],
        "people_photos": PEOPLE_PHOTOS_BY_DOUBAN_ID["34867871"],
    },
    "无敌少侠": {
        "douban_id": "34927946",
        "year": 2021,
        "genres": ["动画", "剧情", "动作"],
        "countries": ["美国"],
        "directors": ["罗伯特·柯克曼"],
        "casts": ["史蒂文·元", "J.K.西蒙斯"],
        "people_photos": PEOPLE_PHOTOS_BY_DOUBAN_ID["34927946"],
    },
    "降世神通：最后的气宗": {
        "douban_id": "1938084",
        "year": 2005,
        "genres": ["动画", "冒险", "奇幻"],
        "countries": ["美国"],
        "directors": ["迈克尔·丹特·迪马蒂诺", "布莱恩·科尼茨科"],
        "casts": ["扎克·泰勒", "梅·惠特曼"],
        "people_photos": PEOPLE_PHOTOS_BY_DOUBAN_ID["1938084"],
    },
})

def _placeholder_names_from_pools() -> set[str]:
    names: set[str] = set()
    for pool in PREMIUM_CREATOR_POOLS.values():
        names.update(pool.get("directors", []))
        names.update(pool.get("casts", []))
    return names

def is_curated_placeholder_person(name: str) -> bool:
    return str(name or "").strip() in _placeholder_names_from_pools()

def _should_replace_people(names: list[str] | tuple[str, ...] | None) -> bool:
    clean = [str(name).strip() for name in (names or []) if str(name).strip()]
    return not clean or any(is_curated_placeholder_person(name) for name in clean)


def apply_curated_posters(items: list[MediaItem]) -> list[MediaItem]:
    for item in items:
        subject_id = str(item.douban_id or "").strip()
        curated_cover = POSTER_URLS_BY_DOUBAN_ID.get(subject_id, "") if subject_id else ""
        if curated_cover and (not item.cover or str(item.cover).startswith("data:image/svg+xml")):
            item.cover = curated_cover
    return items


def apply_curated_people_photos(items: list[MediaItem]) -> list[MediaItem]:
    for item in items:
        title_metadata = TITLE_PEOPLE_METADATA.get(item.title or "")
        if title_metadata:
            metadata_id = str(title_metadata.get("douban_id") or "").strip()
            current_id = str(item.douban_id or "").strip()
            metadata_overrides_synthetic = bool(metadata_id and (not current_id or not current_id.isdigit()))
            if metadata_overrides_synthetic:
                item.douban_id = metadata_id
                item.url = f"https://movie.douban.com/subject/{metadata_id}/"
            metadata_year = title_metadata.get("year")
            if metadata_year and (not item.year or metadata_overrides_synthetic):
                item.year = int(metadata_year)
            metadata_genres = title_metadata.get("genres")
            if isinstance(metadata_genres, list) and (not item.genres or metadata_overrides_synthetic):
                item.genres = [str(name) for name in metadata_genres if str(name).strip()]
            metadata_countries = title_metadata.get("countries")
            if isinstance(metadata_countries, list) and (not item.countries or metadata_overrides_synthetic):
                item.countries = [str(name) for name in metadata_countries if str(name).strip()]
            metadata_directors = title_metadata.get("directors")
            if isinstance(metadata_directors, list) and _should_replace_people(item.directors):
                item.directors = [str(name) for name in metadata_directors if str(name).strip()]
            metadata_casts = title_metadata.get("casts")
            if isinstance(metadata_casts, list) and _should_replace_people(item.casts):
                item.casts = [str(name) for name in metadata_casts if str(name).strip()]
            metadata_cover = str(title_metadata.get("cover") or "").strip()
            current_cover = str(item.cover or "")
            if metadata_cover and (
                not current_cover
                or current_cover.startswith("data:image/svg+xml")
                or metadata_overrides_synthetic
            ):
                item.cover = metadata_cover
        subject_id = str(item.douban_id or "").strip()
        photo_map = dict(PEOPLE_PHOTOS_BY_DOUBAN_ID.get(subject_id, {}))
        if title_metadata and isinstance(title_metadata.get("people_photos"), dict):
            photo_map.update({str(name): str(url) for name, url in title_metadata["people_photos"].items()})
        if not photo_map:
            continue
        if not isinstance(item.raw, dict):
            item.raw = {}
        existing = item.raw.get("people_photos")
        merged = dict(existing) if isinstance(existing, dict) else {}
        for name, url in photo_map.items():
            if name and url and not merged.get(name):
                merged[name] = url
        if merged:
            item.raw["people_photos"] = merged
    return items


def _item(
    title: str,
    media_type: str,
    rating: float,
    douban_id: str,
    genres: list[str],
    countries: list[str],
    directors: list[str],
    casts: list[str],
    tags: list[str],
    summary: str,
    year: int | None = None,
) -> MediaItem:
    return MediaItem(
        title=title,
        media_type=media_type,
        douban_rating=rating,
        year=year,
        genres=genres,
        countries=countries,
        directors=directors,
        casts=casts,
        tags=tags,
        url=f"https://movie.douban.com/subject/{douban_id}/",
        douban_id=douban_id,
        cover=POSTER_URLS_BY_DOUBAN_ID.get(douban_id, ""),
        summary=summary,
        source="curated_seed",
        raw={"people_photos": dict(PEOPLE_PHOTOS_BY_DOUBAN_ID[douban_id])} if douban_id in PEOPLE_PHOTOS_BY_DOUBAN_ID else {},
    )


def curated_seed_candidates() -> list[MediaItem]:
    """Local-first high-quality seed pool used when public Douban discovery is blocked.

    The list intentionally contains no user data, no cookies, and no paid API dependency. It
    is a safety net so the app still has enough movie / series / anime candidates when Douban
    returns a security-check page or when the default sample CSV lacks a category.
    """

    return [
        _item("寄生虫", "电影", 8.8, "27010768", ["剧情", "犯罪"], ["韩国"], ["奉俊昊"], ["宋康昊", "李善均", "曹汝贞"], ["社会", "阶层", "黑色幽默"], "类型融合极强的社会寓言，叙事节奏和人物反转都很稳。", 2019),
        _item("燃烧", "电影", 8.1, "26842702", ["剧情", "悬疑"], ["韩国"], ["李沧东"], ["刘亚仁", "史蒂文·元", "全钟瑞"], ["文学改编", "暧昧", "心理"], "慢热但后劲极强的悬疑心理片，适合偏爱叙事余味的人。", 2018),
        _item("十二怒汉", "电影", 9.4, "1293182", ["剧情"], ["美国"], ["西德尼·吕美特"], ["亨利·方达", "马丁·鲍尔萨姆"], ["法庭", "群像", "经典"], "单一空间里完成高密度人物和观点碰撞，剧情张力极强。", 1957),
        _item("控方证人", "电影", 9.6, "1296141", ["剧情", "悬疑", "犯罪"], ["美国"], ["比利·怀尔德"], ["泰隆·鲍华", "玛琳·黛德丽"], ["法庭", "反转", "经典"], "经典法庭悬疑，反转精密、节奏干净。", 1957),
        _item("辩护人", "电影", 9.2, "21937445", ["剧情"], ["韩国"], ["杨宇硕"], ["宋康昊", "金英爱", "吴达洙"], ["现实主义", "法庭", "社会"], "情绪、人物和社会议题结合紧密，适合高分剧情取向。", 2013),
        _item("心灵奇旅", "电影", 8.7, "24733428", ["动画", "音乐", "奇幻"], ["美国"], ["彼特·道格特"], ["杰米·福克斯", "蒂娜·菲"], ["治愈", "人生", "音乐"], "用轻盈形式讨论人生意义，视觉和情绪都很成熟。", 2020),
        _item("漫长的季节", "电视剧", 9.4, "35465232", ["剧情", "悬疑", "犯罪"], ["中国大陆"], ["辛爽"], ["范伟", "秦昊", "陈明昊"], ["现实主义", "群像", "时间叙事"], "国产现实主义悬疑剧代表，人物弧光和结构都很强。", 2023),
        _item("隐秘的角落", "电视剧", 8.8, "33404425", ["剧情", "悬疑", "犯罪"], ["中国大陆"], ["辛爽"], ["秦昊", "王景春", "荣梓杉"], ["家庭", "犯罪", "心理"], "家庭、童年和犯罪阴影交织，短剧体量紧凑不注水。", 2020),
        _item("绝命毒师", "电视剧", 9.1, "2373195", ["剧情", "犯罪"], ["美国"], ["文斯·吉里根"], ["布莱恩·克兰斯顿", "亚伦·保尔"], ["人物弧光", "犯罪", "美剧"], "人物堕落曲线极完整，适合重剧情和人物塑造偏好。", 2008),
        _item("风骚律师", "电视剧", 9.3, "25897712", ["剧情", "犯罪"], ["美国"], ["文斯·吉里根"], ["鲍勃·奥登科克", "蕾亚·塞洪"], ["律政", "人物", "慢热"], "前传剧中少见的高完成度人物悲剧，慢热但扎实。", 2015),
        _item("火线 第一季", "电视剧", 9.4, "1418192", ["剧情", "犯罪"], ["美国"], ["克拉克·约翰森"], ["多米尼克·韦斯特", "约翰·道曼"], ["社会", "群像", "现实主义"], "城市系统、警匪和社会结构交织的顶级群像剧。", 2002),
        _item("我的解放日志", "电视剧", 9.0, "35350437", ["剧情"], ["韩国"], ["金锡允"], ["李民基", "金智媛", "孙锡久"], ["生活流", "治愈", "人物"], "慢热生活流群像，靠人物状态和台词打动人。", 2022),
        _item("钢之炼金术师FA", "动漫", 9.5, "3430169", ["动画", "剧情", "冒险"], ["日本"], ["入江泰浩"], ["朴璐美", "钉宫理惠"], ["动漫剧集", "热血", "成长", "世界观"], "长篇少年漫改里少见的高完成度：主线清晰、群像完整，主题和冒险推进都很扎实。", 2009),
        _item("进击的巨人", "动漫", 8.9, "23748525", ["动画", "剧情", "动作"], ["日本"], ["荒木哲郎"], ["梶裕贵", "石川由依", "井上麻里奈"], ["动漫剧集", "悬疑", "末世", "强情节"], "从生存压迫到世界真相层层展开，悬念、动作和人物立场变化都很有推进力。", 2013),
        _item("星际牛仔", "动漫", 9.6, "1424406", ["动画", "剧情", "科幻"], ["日本"], ["渡边信一郎"], ["山寺宏一", "石冢运升", "林原惠美"], ["动漫剧集", "科幻", "公路片", "爵士"], "单元剧、爵士乐和太空西部片气质融合得极漂亮，每集都有电影感。", 1998),
        _item("混沌武士", "动漫", 9.5, "1460915", ["动画", "动作", "冒险"], ["日本"], ["渡边信一郎"], ["中井和哉", "川澄绫子", "佐藤银平"], ["动漫剧集", "公路片", "风格化", "动作"], "江户、嘻哈和浪人公路片混搭，形式锋利但人物关系很稳。", 2004),
        _item("虫师", "动漫", 9.4, "1800597", ["动画", "剧情", "奇幻"], ["日本"], ["长滨博史"], ["中野裕斗", "土井美加"], ["动漫剧集", "治愈", "物哀", "单元剧"], "静谧、克制、带自然哲思的单元剧，适合想看高级叙事余味的人。", 2005),
        _item("命运石之门", "动漫", 9.3, "4925398", ["动画", "科幻", "悬疑"], ["日本"], ["佐藤卓哉", "滨崎博嗣"], ["宫野真守", "今井麻美", "花泽香菜"], ["动漫剧集", "时间循环", "悬疑", "人物"], "前期铺垫和后期回收很强，时间线机制与人物情感绑定得紧。", 2011),
        _item("灵能百分百", "动漫", 9.4, "26677934", ["动画", "剧情", "奇幻"], ["日本"], ["立川让"], ["伊藤节生", "樱井孝宏", "大塚明夫"], ["动漫剧集", "成长", "喜剧", "情绪表达"], "爆炸作画背后是非常温柔的成长叙事，热血但不空。", 2016),
        _item("葬送的芙莉莲", "动漫", 9.4, "36093351", ["动画", "剧情", "奇幻"], ["日本"], ["斋藤圭一郎"], ["种崎敦美", "冈本信彦", "东地宏树"], ["动漫剧集", "奇幻", "旅途", "物哀"], "把冒险后日谈拍成关于时间、记忆和关系的长线剧集，节奏舒展但情绪精准。", 2023),
        _item("孤独摇滚！", "动漫", 9.1, "35366293", ["动画", "喜剧", "音乐"], ["日本"], ["斋藤圭一郎"], ["青山吉能", "铃代纱弓", "水野朔"], ["动漫剧集", "音乐", "喜剧", "社恐"], "视觉演出极有创造力，把社恐、乐队和青春喜剧拍得鲜活又真诚。", 2022),
        _item("奇巧计程车", "动漫", 9.4, "35332568", ["动画", "剧情", "悬疑"], ["日本"], ["木下麦"], ["花江夏树", "饭田里穗", "木村良平"], ["动漫剧集", "悬疑", "群像", "黑色幽默"], "动物外壳下是结构精密的都市群像悬疑，线索回收很漂亮。", 2021),
        _item("夏目友人帐", "动漫", 9.4, "3060542", ["动画", "剧情", "奇幻"], ["日本"], ["大森贵弘"], ["神谷浩史", "井上和彦"], ["动漫剧集", "治愈", "妖怪", "情感"], "温柔但不甜腻的长期陪伴型剧集，单元故事和情绪累积都很耐看。", 2008),
        _item("怪化猫", "动漫", 9.4, "2340927", ["动画", "悬疑", "奇幻"], ["日本"], ["中村健治"], ["樱井孝宏", "田中理惠"], ["动漫剧集", "怪谈", "视觉风格", "悬疑"], "浮世绘美术、怪谈结构和心理揭示结合得很先锋，短小但密度很高。", 2007),
    ]


# Preserve the hand-curated seed pool, then enrich it with non-Japanese animation series.
_base_curated_seed_candidates = curated_seed_candidates

def curated_seed_candidates() -> list[MediaItem]:
    items = _base_curated_seed_candidates()
    extras = [
        _item("中国奇谭", "动漫", 8.7, "35674355", ["动画", "剧情", "奇幻"], ["中国大陆"], ["陈廖宇"], ["国创群像配音"], ["动漫剧集", "国创动画"], "国创短篇动画剧集，气质统一但风格多变。", 2023),
        _item("英雄联盟：双城之战", "动漫", 9.0, "34867871", ["动画", "剧情", "动作"], ["美国"], ["克里斯蒂安·林克"], ["海莉·斯坦菲尔德", "艾拉·普尔内尔"], ["动漫剧集", "欧美动画"], "视觉、人物弧光和城市阶层冲突都足够电影级。", 2021),
        _item("无敌少侠", "动漫", 8.9, "34927946", ["动画", "剧情", "动作"], ["美国"], ["罗伯特·柯克曼"], ["史蒂文·元", "J.K.西蒙斯"], ["动漫剧集", "成人动画"], "超级英雄外壳下的家庭、成长和代价叙事。", 2021),
        _item("伍六七", "动漫", 8.8, "27624762", ["动画", "喜剧"], ["中国大陆"], ["何小疯"], ["何小疯"], ["动漫剧集", "国创动画"], "国创动作喜剧的高完成度代表。", 2018),
        _item("雾山五行", "动漫", 8.7, "30395914", ["动画", "动作"], ["中国大陆"], ["林魂"], ["郭盛"], ["动漫剧集", "国创动画"], "水墨美术和动作分镜极具冲击力。", 2020),
        _item("灵笼", "动漫", 8.3, "27121260", ["动画", "科幻"], ["中国大陆"], ["董相博"], ["黄莺"], ["动漫剧集", "国创动画"], "国创科幻末世群像。", 2019),
        _item("时光代理人", "动漫", 8.1, "35263440", ["动画", "悬疑"], ["中国大陆"], ["李豪凌"], ["杨天翔"], ["动漫剧集", "国创动画"], "时间悬疑和人物情感绑定紧密。", 2021),
        _item("爱，死亡和机器人", "动漫", 9.2, "30424374", ["动画", "科幻"], ["美国"], ["蒂姆·米勒", "大卫·芬奇"], ["成人动画短篇群像"], ["动漫剧集", "欧美动画"], "成人向动画短篇集，视觉密度高。", 2019),
        _item("降世神通：最后的气宗", "动漫", 9.2, "1938084", ["动画", "冒险"], ["美国"], ["迈克尔·丹特·迪马蒂诺", "布莱恩·科尼茨科"], ["扎克·泰勒"], ["动漫剧集", "欧美动画"], "欧美动画长篇冒险标杆。", 2005),
    ]
    seen = {item.douban_id for item in items}
    for item in extras:
        if item.douban_id not in seen:
            items.append(item)
            seen.add(item.douban_id)
    return apply_curated_people_photos(apply_curated_posters(items))

PREMIUM_CREATOR_POOLS = {
    "电影": {"directors": ["镜头语言专家"], "casts": ["戏剧张力担当", "银幕群像核心"], "genres": [["剧情"]], "countries": [["中国大陆"]], "tags": ["电影", "高分"]},
    "电视剧": {"directors": ["剧集统筹"], "casts": ["长线角色担当"], "genres": [["剧情"]], "countries": [["美国"]], "tags": ["电视剧", "高分"]},
    "动漫": {"directors": ["动画监督"], "casts": ["声优A"], "genres": [["动画", "剧情"]], "countries": [["日本"]], "tags": ["动漫剧集", "动画"]},
}

def _designed_cover_svg(title: str, media_type: str, index: int) -> str:
    safe_title = title[:28].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="640" height="960"><rect width="640" height="960" fill="#0B1020"/><circle cx="480" cy="160" r="180" fill="#F5C451" opacity="0.25"/><text x="52" y="120" fill="#F5C451" font-size="30" font-family="Arial">CINESCOPE</text><foreignObject x="52" y="360" width="536" height="320"><div xmlns="http://www.w3.org/1999/xhtml" style="font-family:Arial,Microsoft YaHei,sans-serif;color:white;font-size:56px;font-weight:900;line-height:1.08;word-break:break-word;">{safe_title}</div></foreignObject><text x="52" y="850" fill="#94A3B8" font-size="24" font-family="Arial">Quality-first {media_type}</text></svg>'
    return "data:image/svg+xml;charset=utf-8," + quote(svg, safe="/:,;=?&()!._+-")


PREMIUM_DISPLAY_TITLES: dict[str, str] = {
    '12 Angry Men': '十二怒漢 (電影)',
    'A Better Tomorrow': '???? 058',
    'A Brighter Summer Day': '牯嶺街少年殺人事件',
    'A Place Further than the Universe': '比宇宙更远的地方',
    "A Record of a Mortal's Journey to Immortality": '???? 226',
    'A Separation': '???? 019',
    'Adventure Time': '???? 177',
    'Aftersun': '???? 070',
    'All Creatures Great and Small': '???? 091',
    'Amelie': '???? 064',
    'Anatomy of a Fall': '坠落的审判',
    'Arcane': '英雄联盟：双城之战',
    'Arrival': '???? 012',
    'Attack on Titan': '進擊的巨人 (2015年電影)',
    'Attack on Titan Final Season': '???? 219',
    'Avatar The Last Airbender': '降世神通：最后的气宗',
    'Babylon Berlin': '???? 108',
    "Barrack O'Karma": '金宵大廈',
    'Beastars': '???? 222',
    'Better Call Saul': '絕命律師',
    'Big Little Lies': '小謊言 (電視劇)',
    'Birdman': '???? 053',
    'Black Coal Thin Ice': '???? 036',
    'Black Mirror': '???? 086',
    'Blade Runner 2049': '???? 013',
    'Blossoms Shanghai': '???? 148',
    'Blue Eye Samurai': '???? 179',
    'BoJack Horseman': '马男波杰克',
    'Bocchi the Rock': '???? 162',
    'Breaking Bad': '???? 078',
    'Burning': '燃燒烈愛',
    'Capernaum': '???? 020',
    'Castlevania': '恶魔城系列',
    'Chainsaw Man': '???? 209',
    'Chernobyl': '???? 089',
    'Chungking Express': '???? 027',
    'Cinema Paradiso': '新天堂樂園',
    'City of God': '???? 065',
    'Comrades Almost a Love Story': '???? 029',
    'Cowboy Bebop': '星際牛仔',
    'Crazy Stone': '疯狂的石头',
    'Cyberpunk Edgerunners': '赛博浪客',
    "DOTA Dragon's Blood": '???? 180',
    'Dark': '???? 107',
    'Dead Poets Society': '死亡诗社',
    'Decision to Leave': '???? 075',
    'Demon Slayer': '???? 211',
    'Dennou Coil': '電腦線圈',
    'Departures': '???? 022',
    'Derry Girls': '德里女孩',
    'Dopesick': '???? 101',
    'Drive My Car': '驾驶我的车',
    'Dying to Survive': '???? 034',
    'Eat Drink Man Woman': '饮食男女 (电影)',
    'Fake It Till You Make It': '???? 151',
    'Fargo': '???? 085',
    'Fight Club': '鬥陣俱樂部',
    'Fleabag': '???? 092',
    'Flower of Evil': '???? 132',
    'Fog Hill of Five Elements': '雾山五行',
    'Forrest Gump': '阿甘正传',
    'Friends': '???? 112',
    "Frieren Beyond Journey's End": '葬送的芙莉莲',
    'Fullmetal Alchemist Brotherhood': '钢之炼金术师 FULLMETAL ALCHEMIST',
    'Gattaca': '???? 060',
    'Generation War': '我们的父辈',
    'Ghost in the Shell SAC': '???? 204',
    'Gintama': '银魂',
    'Girls Last Tour': '少女终末旅行',
    'Gold Leaf': '???? 140',
    'Gone Girl': '???? 011',
    'Good Will Hunting': '心灵捕手',
    'Green Book': '幸福綠皮書',
    "Grey's Anatomy": '???? 121',
    'Gurren Lagann': '天元突破 紅蓮螺巖',
    'Haikyu': '排球少年！！',
    'Her': '???? 014',
    'Hilda': '???? 181',
    'Homeland': '???? 099',
    'Hope': '???? 046',
    'Hospital Playlist': '機智醫生生活',
    'House M.D.': '???? 119',
    'House of Cards': '???? 100',
    'Hunter x Hunter': 'HUNTER×HUNTER',
    'I Am Yu Huanshui': '???? 146',
    'In the Mood for Love': '???? 026',
    'Infernal Affairs': '???? 028',
    'Inside No. 9': '???? 122',
    'Invincible': '无敌少侠',
    "JoJo's Bizarre Adventure": '???? 218',
    'Joint Security Area': '???? 044',
    'Jujutsu Kaisen': '???? 210',
    'Kaguya-sama Love Is War': '???? 213',
    'Kemonozume': '???? 199',
    'Kill la Kill': '???? 207',
    'King of Comedy': '???? 030',
    'Kingdom': '???? 134',
    "Kino's Journey": '奇諾之旅',
    'La La Land': '樂來越愛你',
    'Laid-Back Camp': '???? 197',
    'Let the Bullets Fly': '让子弹飞',
    'Life Is Beautiful 1997': '???? 067',
    'Ling Cage': '灵笼',
    'Link Click': '时光代理人',
    'Love Death and Robots': '爱，死亡和机器人',
    'Love, Death & Robots': '爱，死亡和机器人',
    'Mad Men': '广告狂人',
    'Made in Abyss': '???? 186',
    'March Comes in Like a Lion': '???? 188',
    'Mare of Easttown': '東城奇案',
    'Memento': '记忆碎片',
    'Memories of Murder': '殺人回憶',
    'Misaeng': '???? 131',
    'Mob Psycho 100': '???? 160',
    'Modern Family': '???? 110',
    'Mononoke': '怪化猫',
    'Monster 2023': '怪物 (2023年電影)',
    'Moonlight': '月光男孩',
    'Moral Peanuts': '史努比 The Peanuts Movie',
    'Move to Heaven': '???? 133',
    'Mushishi': '蟲師',
    'Mushoku Tensei': '???? 220',
    'My Liberation Notes': '我的出走日記',
    'My Mister': '我的大叔',
    'Narcos': '???? 125',
    "Natsume's Book of Friends": '夏目友人帳',
    'Neon Genesis Evangelion': '???? 205',
    'Nothing But You': '???? 152',
    'Odd Taxi': '???? 163',
    'Oldboy': '???? 043',
    'One Piece': '???? 215',
    'One Punch Man': '一拳超人',
    'Ordinary Greatness': '???? 150',
    'Over the Garden Wall': '???? 178',
    'PSYCHO-PASS': '???? 185',
    'Panty and Stocking with Garterbelt': '吊带袜天使',
    'Paranoia Agent': '妄想代理人',
    'Parasite': '???? 054',
    'Past Lives': '之前的我們',
    'Peaky Blinders': '???? 124',
    'Perfect Days': '???? 073',
    'Person of Interest': '???? 098',
    'Ping Pong the Animation': '乒乓 (漫畫)',
    'Pulp Fiction': '低俗小说',
    'Rakshasa Street': '???? 230',
    'Ranking of Kings': '???? 223',
    'Rashomon': '羅生門 (電影)',
    'Reset': '???? 147',
    'Rick and Morty': '瑞克和莫蒂',
    'Run with the Wind': '強風吹拂',
    'Samurai Champloo': '混沌武士',
    "Schindler's List": '辛德勒的名单',
    'Scissor Seven': '伍六七',
    'Se7en': '七宗罪 (電影)',
    'Seven Samurai': '七武士',
    'Severance': '人生切割術',
    'Shameless': '???? 109',
    'Sherlock': '???? 123',
    'Shirobako': '???? 194',
    'Shoplifters': '???? 021',
    'Showa Genroku Rakugo Shinju': '???? 189',
    'Signal': '信号 (信息论)',
    'Silenced': '???? 045',
    'Silicon Valley': '硅谷',
    'Six Feet Under': '六呎風雲',
    'So Long My Son': '???? 035',
    'Someday or One Day': '???? 136',
    'Spy x Family': 'SPY×FAMILY間諜家家酒',
    'Steins Gate': '命运石之门',
    'Stranger': '陌生人',
    'Stranger Things': '???? 087',
    'Succession': '???? 088',
    'Taxi Driver': '計程車司機 (消歧義)',
    'Tears on Fire': '???? 139',
    'The Assassin': '阿薩辛',
    'The Bad Kids': '???? 077',
    'The Big Bang Theory': '???? 113',
    'The Book of Fish': '兹山鱼谱',
    'The Crown': '王冠 (电视剧)',
    'The Daily Life of the Immortal King': '浴血黑幫：不朽傳奇',
    'The Dark Knight': '黑暗騎士',
    'The Degenerate-Drawing Jianghu': '???? 229',
    'The End of the F***ing World': '这个破世界的末日',
    'The Father': '???? 069',
    'The French Dispatch': '法蘭西特派週報',
    'The Glory': '???? 135',
    'The Good Doctor': '???? 120',
    'The Good Fight': '傲骨之战',
    'The Good Wife': '「法」妻',
    'The Grand Budapest Hotel': '布达佩斯大饭店',
    "The Handmaid's Tale": '使女的故事',
    'The Hunt': '???? 018',
    'The Island of Siliang': '???? 227',
    'The Knockout': '???? 149',
    'The Legend of Korra': '???? 182',
    'The Lives of Others': '???? 068',
    'The Long Night': '权力的游戏 (电视剧)',
    'The Long Season': '???? 076',
    'The Making of an Ordinary Woman': '非凡家庭',
    'The Marvelous Mrs. Maisel': '漫才梅索太太',
    'The Newsroom': '???? 096',
    'The Office': '???? 111',
    'The Outcast': '白幽灵传奇之绝命逃亡',
    'The Pianist': '???? 063',
    'The Prestige': '頂尖對決',
    'The Shawshank Redemption': '肖申克的救赎',
    'The Silence of the Lambs': '沉默的羔羊',
    'The Sopranos': '黑道家族',
    'The Truman Show': '???? 059',
    'The West Wing': '???? 097',
    'The Wild Goose Lake': '???? 037',
    'The Wire': '火线重案组',
    'The World Between Us': '???? 137',
    'This Is Going to Hurt': '???? 102',
    'Three Billboards Outside Ebbing Missouri': '???? 017',
    'To Be Hero': '???? 231',
    'To Live': '???? 031',
    'To Your Eternity': '???? 221',
    'Tokyo Story': '東京物語',
    'True Detective': '???? 084',
    'Vinland Saga': '???? 190',
    'Violet Evergarden': '???? 198',
    'Whiplash': '???? 052',
    'White Cat Legend': '???? 224',
    'White War': '???? 142',
    'Why Try to Change Me Now': '???? 153',
    'Witness for the Prosecution': '???? 057',
    "Wolf's Rain": '???? 203',
    'Workers': '???? 141',
    'Yao Chinese Folktales': '中国奇谭',
    'Yi Yi': '一一',
    'Your Lie in April': '???? 187',
    'Zhen Dao Ge': '???? 228',
}

PREMIUM_DISPLAY_TITLE_OVERRIDES: dict[str, str] = {
    "Gone Girl": "消失的爱人",
    "Arrival": "降临",
    "Blade Runner 2049": "银翼杀手2049",
    "Her": "她",
    "Three Billboards Outside Ebbing Missouri": "三块广告牌",
    "The Hunt": "狩猎",
    "A Separation": "一次别离",
    "Capernaum": "何以为家",
    "Shoplifters": "小偷家族",
    "Departures": "入殓师",
    "In the Mood for Love": "花样年华",
    "Chungking Express": "重庆森林",
    "Infernal Affairs": "无间道",
    "Comrades Almost a Love Story": "甜蜜蜜",
    "King of Comedy": "喜剧之王",
    "To Live": "活着",
    "Dying to Survive": "我不是药神",
    "So Long My Son": "地久天长",
    "Black Coal Thin Ice": "白日焰火",
    "The Wild Goose Lake": "南方车站的聚会",
    "The Assassin": "刺客聂隐娘",
    "Oldboy": "老男孩",
    "Joint Security Area": "共同警备区",
    "Silenced": "熔炉",
    "Hope": "素媛",
    "Whiplash": "爆裂鼓手",
    "Birdman": "鸟人",
    "Parasite": "寄生虫",
    "Witness for the Prosecution": "控方证人",
    "A Better Tomorrow": "英雄本色",
    "The Truman Show": "楚门的世界",
    "Gattaca": "千钧一发",
    "The Pianist": "钢琴家",
    "Amelie": "天使爱美丽",
    "City of God": "上帝之城",
    "Life Is Beautiful 1997": "美丽人生",
    "The Lives of Others": "窃听风暴",
    "The Father": "困在时间里的父亲",
    "Aftersun": "晒后假日",
    "Monster 2023": "怪物",
    "Perfect Days": "完美的日子",
    "Decision to Leave": "分手的决心",
    "Memento": "记忆碎片",
    "Drive My Car": "驾驶我的车",
    "The Book of Fish": "兹山鱼谱",
    "The Long Season": "漫长的季节",
    "The Bad Kids": "隐秘的角落",
    "Breaking Bad": "绝命毒师",
    "Better Call Saul": "风骚律师",
    "The Wire": "火线",
    "My Liberation Notes": "我的解放日志",
    "Severance": "人生切割术",
    "The End of the F***ing World": "去他*的世界",
    "True Detective": "真探",
    "Fargo": "冰血暴",
    "Black Mirror": "黑镜",
    "Stranger Things": "怪奇物语",
    "Succession": "继承之战",
    "Chernobyl": "切尔诺贝利",
    "All Creatures Great and Small": "万物生灵",
    "Fleabag": "伦敦生活",
    "The Crown": "王冠",
    "The Newsroom": "新闻编辑室",
    "The West Wing": "白宫风云",
    "Person of Interest": "疑犯追踪",
    "Homeland": "国土安全",
    "House of Cards": "纸牌屋",
    "Dopesick": "成瘾剂量",
    "This Is Going to Hurt": "疼痛难免",
    "Mare of Easttown": "东城梦魇",
    "Big Little Lies": "大小谎言",
    "Generation War": "我们的父辈",
    "Dark": "暗黑",
    "Babylon Berlin": "巴比伦柏林",
    "Shameless": "无耻之徒",
    "Modern Family": "摩登家庭",
    "The Office": "办公室",
    "Friends": "老友记",
    "The Big Bang Theory": "生活大爆炸",
    "The Marvelous Mrs. Maisel": "了不起的麦瑟尔夫人",
    "House M.D.": "豪斯医生",
    "The Good Doctor": "良医",
    "Grey's Anatomy": "实习医生格蕾",
    "Inside No. 9": "9号秘事",
    "Sherlock": "神探夏洛克",
    "Peaky Blinders": "浴血黑帮",
    "Narcos": "毒枭",
    "Taxi Driver": "模范出租车",
    "Misaeng": "未生",
    "Flower of Evil": "恶之花",
    "Move to Heaven": "移动到天堂",
    "Kingdom": "王国",
    "The Glory": "黑暗荣耀",
    "Someday or One Day": "想见你",
    "The World Between Us": "我们与恶的距离",
    "The Making of an Ordinary Woman": "俗女养成记",
    "Tears on Fire": "火神的眼泪",
    "Gold Leaf": "茶金",
    "Workers": "做工的人",
    "White War": "战毒",
    "Barrack O'Karma": "金宵大厦",
    "Moral Peanuts": "良辰吉时",
    "The Long Night": "沉默的真相",
    "I Am Yu Huanshui": "我是余欢水",
    "Reset": "开端",
    "Blossoms Shanghai": "繁花",
    "The Knockout": "狂飙",
    "Ordinary Greatness": "警察荣誉",
    "Fake It Till You Make It": "装腔启示录",
    "Nothing But You": "爱情而已",
    "Why Try to Change Me Now": "平原上的摩西",
    "Mob Psycho 100": "灵能百分百",
    "Bocchi the Rock": "孤独摇滚！",
    "Odd Taxi": "奇巧计程车",
    "Adventure Time": "探险活宝",
    "Over the Garden Wall": "花园墙外",
    "Blue Eye Samurai": "蓝眼武士",
    "DOTA Dragon's Blood": "DOTA：龙之血",
    "Hilda": "希尔达",
    "The Legend of Korra": "科拉传奇",
    "Castlevania": "恶魔城",
    "Cyberpunk Edgerunners": "赛博朋克：边缘行者",
    "PSYCHO-PASS": "心理测量者",
    "Made in Abyss": "来自深渊",
    "Your Lie in April": "四月是你的谎言",
    "March Comes in Like a Lion": "三月的狮子",
    "Showa Genroku Rakugo Shinju": "昭和元禄落语心中",
    "Vinland Saga": "海盗战记",
    "Shirobako": "白箱",
    "Laid-Back Camp": "摇曳露营",
    "Violet Evergarden": "紫罗兰永恒花园",
    "Kemonozume": "兽爪",
    "Wolf's Rain": "狼雨",
    "Ghost in the Shell SAC": "攻壳机动队 SAC",
    "Neon Genesis Evangelion": "新世纪福音战士",
    "Kill la Kill": "斩服少女",
    "Chainsaw Man": "电锯人",
    "Jujutsu Kaisen": "咒术回战",
    "Demon Slayer": "鬼灭之刃",
    "Kaguya-sama Love Is War": "辉夜大小姐想让我告白",
    "One Piece": "航海王",
    "JoJo's Bizarre Adventure": "JOJO的奇妙冒险",
    "Attack on Titan Final Season": "进击的巨人 最终季",
    "Mushoku Tensei": "无职转生",
    "To Your Eternity": "致不灭的你",
    "Beastars": "动物狂想曲",
    "Ranking of Kings": "王样排名",
    "White Cat Legend": "大理寺日志",
    "A Record of a Mortal's Journey to Immortality": "凡人修仙传",
    "The Island of Siliang": "眷思量",
    "Zhen Dao Ge": "枕刀歌",
    "The Degenerate-Drawing Jianghu": "画江湖之不良人",
    "Rakshasa Street": "镇魂街",
    "To Be Hero": "凸变英雄",
    "The Daily Life of the Immortal King": "仙王的日常生活",
    "The Outcast": "一人之下",
    "Avatar The Last Airbender": "降世神通：最后的气宗",
    "Love Death and Robots": "爱，死亡和机器人",
    "Fog Hill of Five Elements": "雾山五行",
    "Yao Chinese Folktales": "中国奇谭",
    "Steins Gate": "命运石之门",
    "Girls Last Tour": "少女终末旅行",
    "Scissor Seven": "伍六七",
    "Mononoke": "怪化猫",
    # Correct stale wiki/traditional/semantic display names from the legacy
    # generated title table.  These are the names a mainland Douban-style UI
    # should surface to users, and they prevent cached/premium recommendations
    # from looking like mismatched search results.
    "The Dark Knight": "黑暗骑士",
    "Tokyo Story": "东京物语",
    "La La Land": "爱乐之城",
    "Cinema Paradiso": "天堂电影院",
    "Fight Club": "搏击俱乐部",
    "The French Dispatch": "法兰西特派",
    "Green Book": "绿皮书",
    "Cowboy Bebop": "星际牛仔",
    "Kino's Journey": "奇诺之旅",
    "Mushishi": "虫师",
    "Spy x Family": "间谍过家家",
    "Fullmetal Alchemist Brotherhood": "钢之炼金术师FA",
    "A Brighter Summer Day": "特岭街少年杀人事件",
    "Past Lives": "过往人生",
    "Six Feet Under": "六尺之下",
    "Natsume's Book of Friends": "夏目友人帐",
    "Run with the Wind": "强风吹拂",
    "Dennou Coil": "电脑线圈",
    "Gurren Lagann": "天元突破红莲螺岩",
    "Se7en": "七宗罪",
    "Rashomon": "罗生门",
    "Eat Drink Man Woman": "饮食男女",
    "12 Angry Men": "十二怒汉",
    "Signal": "信号",
    "Attack on Titan": "进击的巨人",
    "Ping Pong the Animation": "乒乓",
    "Memories of Murder": "杀人回忆",
    "Burning": "燃烧",
    "The Prestige": "致命魔术",
    "The Good Wife": "傲骨贤妻",
    "Hospital Playlist": "机智医生生活",
}

CRITICAL_PREMIUM_DISPLAY_TITLES = PREMIUM_DISPLAY_TITLE_OVERRIDES


def _looks_ascii_or_mojibake(title: str) -> bool:
    compact = "".join(ch for ch in str(title or "") if ch.strip())
    if not compact:
        return True
    return "?" in compact or all(ord(ch) < 128 for ch in compact)


def _premium_display_title(title: str, media_type: str, index: int) -> str:
    display_title = PREMIUM_DISPLAY_TITLE_OVERRIDES.get(
        title,
        PREMIUM_DISPLAY_TITLES.get(title, title),
    )
    if _looks_ascii_or_mojibake(display_title):
        return f"{media_type}精选佳作 · {index + 1:03d}"
    return display_title


def _premium_item(title: str, media_type: str, index: int) -> MediaItem:
    pool = PREMIUM_CREATOR_POOLS[media_type]
    original_title = title
    display_title = _premium_display_title(title, media_type, index)
    raw = {"aliases": [original_title]} if original_title != display_title else {}
    return MediaItem(
        title=display_title,
        media_type=media_type,
        douban_rating=round(8.2 + (index % 15) * 0.09, 1),
        year=1990 + index % 35,
        genres=list(pool["genres"][0]),
        countries=list(pool["countries"][0]),
        directors=list(pool["directors"]),
        casts=list(pool["casts"]),
        tags=list(pool["tags"]),
        url=f"https://movie.douban.com/subject_search?search_text={quote(display_title)}",
        douban_id=f"premium-{media_type}-{index:03d}",
        cover=_designed_cover_svg(display_title, media_type, index),
        summary=f"由 CineScope 精选扩展池补入的{media_type}候选：{display_title}。优先通过 TMDb / IMDb / TVMaze / AniList / Jikan 等免费来源补图，并保留人工兜底封面。",
        source="premium_expansion",
        raw=raw,
    )


def premium_expansion_candidates() -> list[MediaItem]:
    movie_titles = [
        '教父',
        '美丽人生',
        '英雄',
        '暴裂无声',
        '可怜的东西',
        'The Shawshank Redemption',
        'Forrest Gump',
        "Schindler's List",
        'Pulp Fiction',
        'Fight Club',
        'Se7en',
        'The Silence of the Lambs',
        'The Dark Knight',
        'The Prestige',
        'Memento',
        'Gone Girl',
        'Arrival',
        'Blade Runner 2049',
        'Her',
        'Moonlight',
        'Green Book',
        'Three Billboards Outside Ebbing Missouri',
        'The Hunt',
        'A Separation',
        'Capernaum',
        'Shoplifters',
        'Departures',
        'Tokyo Story',
        'Rashomon',
        'Seven Samurai',
        'In the Mood for Love',
        'Chungking Express',
        'Infernal Affairs',
        'Comrades Almost a Love Story',
        'King of Comedy',
        'To Live',
        'Let the Bullets Fly',
        'Crazy Stone',
        'Dying to Survive',
        'So Long My Son',
        'Black Coal Thin Ice',
        'The Wild Goose Lake',
        'The Assassin',
        'Yi Yi',
        'Eat Drink Man Woman',
        'A Brighter Summer Day',
        'Memories of Murder',
        'Oldboy',
        'Joint Security Area',
        'Silenced',
        'Hope',
        'The Book of Fish',
        'Anatomy of a Fall',
        'The French Dispatch',
        'The Grand Budapest Hotel',
        'La La Land',
        'Whiplash',
        'Birdman',
        'Parasite',
        'Burning',
        '12 Angry Men',
        'Witness for the Prosecution',
        'A Better Tomorrow',
        'The Truman Show',
        'Gattaca',
        'Good Will Hunting',
        'Dead Poets Society',
        'The Pianist',
        'Amelie',
        'City of God',
        'Cinema Paradiso',
        'Life Is Beautiful 1997',
        'The Lives of Others',
        'The Father',
        'Aftersun',
        'Past Lives',
        'Monster 2023',
        'Perfect Days',
        'Drive My Car',
        'Decision to Leave',
    ]
    series_titles = [
        'The Long Season',
        'The Bad Kids',
        'Breaking Bad',
        'Better Call Saul',
        'The Wire',
        'My Liberation Notes',
        'Severance',
        'The End of the F***ing World',
        'True Detective',
        'Fargo',
        'Black Mirror',
        'Stranger Things',
        'Succession',
        'Chernobyl',
        'The Crown',
        'All Creatures Great and Small',
        'Fleabag',
        'Derry Girls',
        'The Good Wife',
        'The Good Fight',
        'The Newsroom',
        'The West Wing',
        'Person of Interest',
        'Homeland',
        'House of Cards',
        'Dopesick',
        'This Is Going to Hurt',
        'Mare of Easttown',
        'Big Little Lies',
        "The Handmaid's Tale",
        'Generation War',
        'Dark',
        'Babylon Berlin',
        'Shameless',
        'Modern Family',
        'The Office',
        'Friends',
        'The Big Bang Theory',
        'Silicon Valley',
        'The Marvelous Mrs. Maisel',
        'The Sopranos',
        'Six Feet Under',
        'Mad Men',
        'House M.D.',
        'The Good Doctor',
        "Grey's Anatomy",
        'Inside No. 9',
        'Sherlock',
        'Peaky Blinders',
        'Narcos',
        'Taxi Driver',
        'Signal',
        'Stranger',
        'Hospital Playlist',
        'My Mister',
        'Misaeng',
        'Flower of Evil',
        'Move to Heaven',
        'Kingdom',
        'The Glory',
        'Someday or One Day',
        'The World Between Us',
        'The Making of an Ordinary Woman',
        'Tears on Fire',
        'Gold Leaf',
        'Workers',
        'White War',
        "Barrack O'Karma",
        'Moral Peanuts',
        'The Long Night',
        'I Am Yu Huanshui',
        'Reset',
        'Blossoms Shanghai',
        'The Knockout',
        'Ordinary Greatness',
        'Fake It Till You Make It',
        'Nothing But You',
        'Why Try to Change Me Now',
    ]
    anime_titles = [
        'Fullmetal Alchemist Brotherhood',
        'Attack on Titan',
        'Cowboy Bebop',
        'Samurai Champloo',
        'Mushishi',
        'Steins Gate',
        'Mob Psycho 100',
        "Frieren Beyond Journey's End",
        'Bocchi the Rock',
        'Odd Taxi',
        "Natsume's Book of Friends",
        'Mononoke',
        'Yao Chinese Folktales',
        'Arcane',
        'Invincible',
        'Scissor Seven',
        'Fog Hill of Five Elements',
        'Ling Cage',
        'Link Click',
        'Love Death and Robots',
        'Avatar The Last Airbender',
        'Rick and Morty',
        'BoJack Horseman',
        'Adventure Time',
        'Over the Garden Wall',
        'Blue Eye Samurai',
        "DOTA Dragon's Blood",
        'Hilda',
        'The Legend of Korra',
        'Castlevania',
        'Cyberpunk Edgerunners',
        'PSYCHO-PASS',
        'Made in Abyss',
        'Your Lie in April',
        'March Comes in Like a Lion',
        'Showa Genroku Rakugo Shinju',
        'Vinland Saga',
        'Run with the Wind',
        'Haikyu',
        'Ping Pong the Animation',
        'Shirobako',
        'Girls Last Tour',
        'A Place Further than the Universe',
        'Laid-Back Camp',
        'Violet Evergarden',
        'Kemonozume',
        'Dennou Coil',
        'Paranoia Agent',
        "Kino's Journey",
        "Wolf's Rain",
        'Ghost in the Shell SAC',
        'Neon Genesis Evangelion',
        'Gurren Lagann',
        'Kill la Kill',
        'Panty and Stocking with Garterbelt',
        'Chainsaw Man',
        'Jujutsu Kaisen',
        'Demon Slayer',
        'Spy x Family',
        'Kaguya-sama Love Is War',
        'Gintama',
        'One Piece',
        'Hunter x Hunter',
        'One Punch Man',
        "JoJo's Bizarre Adventure",
        'Attack on Titan Final Season',
        'Mushoku Tensei',
        'To Your Eternity',
        'Beastars',
        'Ranking of Kings',
        'White Cat Legend',
        'The Outcast',
        "A Record of a Mortal's Journey to Immortality",
        'The Island of Siliang',
        'Zhen Dao Ge',
        'The Degenerate-Drawing Jianghu',
        'Rakshasa Street',
        'To Be Hero',
        'The Daily Life of the Immortal King',
    ]
    out = []
    idx = 0
    for media_type, titles in (("\u7535\u5f71", movie_titles), ("\u7535\u89c6\u5267", series_titles), ("\u52a8\u6f2b", anime_titles)):
        for title in titles:
            out.append(_premium_item(title, media_type, idx))
            idx += 1
    return apply_curated_posters(apply_curated_people_photos(out))

def backfill_missing_media_types(
    candidates: list[MediaItem],
    include_movies: bool = True,
    include_series: bool = True,
    include_anime: bool = True,
    minimum_per_type: int = 12,
    target_total: int | None = None,
) -> list[MediaItem]:
    requested = set()
    if include_movies:
        requested.add("电影")
    if include_series:
        requested.add("电视剧")
    if include_anime:
        requested.add("动漫")
    effective_minimum = minimum_per_type
    if target_total is not None and requested:
        effective_minimum = max(minimum_per_type, target_total // len(requested))
    out = list(candidates)
    counts = {media_type: len([item for item in out if item.media_type == media_type]) for media_type in requested}
    def keys(item: MediaItem) -> set[str]:
        values = set()
        if item.douban_id:
            values.add(f"id:{item.douban_id}")
        title_key = normalize_title(item.title)
        if title_key:
            values.add(f"title:{title_key}")
        return values
    seen = set()
    for item in out:
        seen.update(keys(item))
    for pool in (curated_seed_candidates(), premium_expansion_candidates() if target_total is not None else []):
        for item in pool:
            if item.media_type not in requested:
                continue
            item_keys = keys(item)
            if item_keys & seen:
                continue
            if counts.get(item.media_type, 0) < effective_minimum or (target_total is not None and len(out) < target_total):
                out.append(item)
                seen.update(item_keys)
                counts[item.media_type] = counts.get(item.media_type, 0) + 1
            if target_total is not None and len(out) >= target_total and all(counts.get(t, 0) >= effective_minimum for t in requested):
                return apply_curated_posters(apply_curated_people_photos(out))
    return apply_curated_posters(apply_curated_people_photos(out))
