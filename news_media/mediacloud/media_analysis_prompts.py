# This script contains LLM prompts for analyzing news articles related to flooding and CRE

ARTICLE_TITLE_SCREENING_FLOOD_PROMPT = """\
You are a news article classifier. Your task is to determine whether a news article \
is about an actual ongoing or past flood or tropical cyclone event based only on the \
article's title and URL.

Classify as true if the article appears to cover:
- The impacts, damage, casualties, displacement, or emergency response related to a specific \
flood event, including any of the following types:
    - Pluvial flooding: caused by heavy rainfall or rainstorms overwhelming drainage systems \
or saturated ground, including flash floods and surface water flooding
    - Fluvial flooding: caused by rivers or streams overflowing their banks, including riverine \
flooding or flooding due to snowmelt
    - Coastal flooding: caused by storm surge, tidal flooding, or wind-driven waves
- The impacts, damage, casualties, emergency response, or recovery efforts related to a specific \
tropical cyclone event, including those referred to as hurricanes, typhoons, or tropical storms

Classify as false if the article appears to cover:
- Flood or storm watches, warnings, or advisories (future-focused)
- Seasonal outlooks, forecasts, or risk modeling
- General or background discussions of flood or tropical cyclone risk not tied to a specific event
- Preparedness guides, insurance, or policy discussions not tied to a specific ongoing or past event
- Other types of disasters or emergencies such as industrial accidents, terrorist attacks, \
infectious disease outbreaks, earthquakes, volcanic eruptions, or wildfires
- Topics unrelated to floods or tropical cyclones
- Articles where a flood or tropical cyclone is mentioned only as background context for a story primarily about another topic

Respond using exactly the following JSON format. Do not include any text outside the JSON object.

{
  "classification"": <true | false>,
  "reasoning": "<One sentence explaining your decision.>"
}
"""

ARTICLE_TITLE_SCREENING_FLOOD_EXAMPLES = [
    {"input":"""
    URL: https://www.ktsa.com/hurricane-milton-makes-landfall-in-florida-as-a-category-3-storm/
    TITLE: Hurricane Milton makes landfall in Florida as a Category 3 storm
    """,
     "output":"""
     {
       "classification": true,
       "reasoning": "The title a specific named hurricane making landfall."
     }
     """},
    
    {"input":"""
    URL: https://www.staradvertiser.com/2024/09/29/breaking-news/at-least-69-dead-after-hurricane-helene-passes-floridas-gulf-coast/
    TITLE: At least 69 dead after Hurricane Helene passes Florida’s Gulf Coast
    """,
     "output":"""
     {
       "classification": true,
       "reasoning": "The title describes casualties arising from a specific named hurricane."
     }
     """},
    
    {"input":"""
    URL: https://people.com/at-least-4-dead-multiple-others-missing-after-rainstorm-devastation-in-west-virginia-11755027
    TITLE: At Least 4 People Dead, Multiple Others Missing After Nearly 30-Minute Rainstorm Causes Devastation in West Virginia
    """,
     "output":"""
     {
       "classification": true,
       "reasoning": "The title describes casualties and devastation from a specific heavy rainfall event, consistent with pluvial flooding."
     }
     """},

    {"input":"""
    URL: https://www.wowktv.com/news/u-s-world/record-rains-cause-flash-flooding-in-tennessee-4-dead/
    TITLE: Record rains cause flash flooding in Tennessee; 4 dead
    """,
     "output":"""
     {
       "classification": true,
       "reasoning": "The title explicitly describes flash flooding caused by record rainfall resulting in casualties, consistent with a specific pluvial flood event."
     }
     """},

    {"input":"""
    URL: http://wqow.com/news/national-news-from-the-associated-press/2018/09/24/florence-evacuations-continue-as-north-carolina-rivers-rise/
    TITLE: Florence: Evacuations continue as North Carolina rivers rise
    """,
     "output":"""
     {
       "classification": true,
       "reasoning": "The title describes active evacuations and rising rivers directly associated with Hurricane Florence, a specific named tropical cyclone, consistent with both emergency response and fluvial flooding criteria."
     }
     """},

    {"input":"""
    URL: https://www.nbcnewyork.com/news/national-international/cuba-without-electricity-after-hurricane-ian-knocks-out-power-grid/3883656/
    TITLE: Cuba Without Electricity After Hurricane Ian Knocks Out Power Grid
    """,
     "output":"""
     {
       "classification": true,
       "reasoning": "The title explicitly describes infrastructure impacts directly caused by a specific named hurricane."
     }
     """},

    {"input":"""
    URL: https://www.navytimes.com/veterans/2017/09/22/puerto-ricos-va-hospital-weathers-hurricane-maria-but-challenges-loom/
    TITLE: Puerto Rico's VA hospital weathers Hurricane Maria, but challenges loom
    """,
     "output":"""
     {
       "classification": true,
       "reasoning": "The title describes the condition of a specific institution in direct response to a named tropical cyclone."
     }
     """},

    {"input":"""
    URL: https://www.wkrg.com/weather/crews-restoring-homes-and-businesses-damaged-by-hurricane-sally/
    TITLE: Crews restoring homes and businesses damaged by Hurricane Sally
    """,
     "output":"""
     {
       "classification": true,
       "reasoning": "The title describes restoration and recovery efforts for homes and businesses damaged by a specific named hurricane."
     }
     """},

    {"input":"""
    URL: http://www.rockportpilot.com/business/article_28b1de32-4863-11ea-a3a0-8782467c7f31.html
    TITLE: Texas Back in Business to host webinar for Hurricane Harvey-affected businesses
    """,
     "output":"""
     {
       "classification": true,
       "reasoning": "The article describes a post-event recovery resource directly aimed at businesses impacted by a specific named hurricane."
     }
     """},
    
    {"input":"""
    URL: https://abcnews.go.com/US/scattered-tornadoes-flash-flooding-risk-impact-texas-gulf/story?id=108185013
    TITLE: More than 13 million in Texas face risk of flash flooding, tornadoes
    """,
     "output":"""
     {
       "classification": false,
       "reasoning": "The title's use of 'face risk of' indicates this is a future-oriented forecast or warning article, not coverage of an actual ongoing or past flood event."
     }
     """},
    
    {"input":"""
    URL: https://www.cbsnews.com/newyork/news/new-jersey-flash-flood-warning/
    TITLE: New Jersey facing another flash flood threat just weeks after deadly storms
    """,
     "output":"""
     {
       "classification": false,
       "reasoning": "Both the URL slug 'flash-flood-warning' and the title's use of 'threat' indicate this is a future-oriented advisory, not coverage of an actual ongoing or past flood event."
     }
     """},

    {"input":"""
    URL: https://denver.cbslocal.com/2021/08/19/interstate-70-closed-glenwood-canyon-possibility-flash-flooding-colorado/
    TITLE: CDOT: I-70 To Remain Closed Through Glenwood Canyon Due To Possibility Of Flash Flooding
    """,
     "output":"""
     {
       "classification": false,
       "reasoning": "Both the title and URL use the word 'possibility,' indicating the road closure is a precautionary measure due to future flood risk rather than coverage of an actual ongoing flood event."
     }
     """},

    {"input":"""
    URL: https://www.vaildaily.com/news/hurricane-idalia-chases-florida-residents-from-the-gulf-coast-as-forecasters-warn-of-storm-surge/
    TITLE: Hurricane Idalia chases Florida residents from the Gulf Coast as forecasters warn of storm surge
    """,
     "output":"""
     {
       "classification": false,
       "reasoning": "Although the title references a specific named hurricane and real displacement of residents, the user of future-oriented warning language suggests that evacuation is a precautionary measure rather than a reaction to realized flood impacts."
     }
     """},
    
    {"input":"""
    URL: https://www.ibtimes.com/marianne-williamson-deletes-tweet-suggesting-power-mind-can-alter-hurricane-dorians-2822222?utm_source=Public&utm_medium=Feed&utm_campaign=Distribution
    TITLE: Marianne Williamson Deletes Tweet Suggesting 'Power Of The Mind' Can Alter Hurricane Dorian's Path
    """,
     "output":"""
     {
       "classification": false,
       "reasoning": "Although the article references a specific named hurricane, the subject of the article is a public figure's social media activity, not the impacts or emergency response of Hurricane Dorian."
     }
     """},
    
    {"input":"""
    URL: https://www.kgw.com/article/news/local/longview-plant-disaster/no-hope-of-finding-survivors-of-washington-paper-mill-tank-implosion-where-9-are-missing-officials/616-7eda0a3c-2b84-4004-a327-094486184cfc
    TITLE: No hope of finding survivors of Washington paper mill tank implosion, where 9 are missing: Officials
    """,
     "output":"""
     {
       "classification": false,
       "reasoning": "Both the title and URL indicate this article is about an industrial accident with no connection to a flood or tropical cyclone event."
     }
     """},

    {"input":"""
    URL: http://www.dailyherald.com/article/20170831/news/308319982/
    TITLE: 10 homes burned, 500 threatened in hard-hit California area
    """,
     "output":"""
     {
       "classification": false,
       "reasoning": "The title's references to homes burned and fire threat strongly indicate a wildfire event, with no connection to a flood or tropical cyclone."
     }
     """},

    {"input":"""
    URL: http://www.bnd.com/news/business/article203044609.html#storylink=rss
    TITLE: The Latest: Storm-felled trees kill 5, including 2 children
    """,
     "output":"""
     {
       "classification": false,
       "reasoning": "The title describes clear casualties from a specific storm event, but the word 'storm' is too ambiguous to determine whether the event is a flood or tropical cyclone versus another storm type such as a tornado or thunderstorm."
     }
     """},

    {"input":"""
    URL: https://keyt.com/politics/cnn-us-politics/2024/10/28/russia-china-and-cuba-spread-misinformation-about-us-hurricane-response-us-official-says/
    TITLE: Russia, China and Cuba spread misinformation about US hurricane response, US official says
    """,
     "output":"""
     {
       "classification": false,
       "reasoning": "Although the title references a hurricane response, the primary subject of the article is foreign misinformation and geopolitics, with the hurricane serving only as background context."
     }
     """},

     {"input":"""
    URL: https://www.sanluisobispo.com/news/nation-world/national/article234698317.html#storylink=rss
    TITLE: Florida man parks Smart car in kitchen so it won’t blow away
    """,
     "output":"""
     {
       "classification": false,
       "reasoning": "Although the Florida setting and 'blow away' language suggest a possible hurricane or tropical storm, the event type is not explicitly stated and the story appears to be primarily a human interest piece about a preparatory action rather than coverage of actual impacts."
     }
     """},

    {"input":"""
    URL: https://www.wxii12.com/article/north-carolina-reidsville-27-pound-channel-catfish-record/44496946
    TITLE: North Carolina man reels in 27 pound channel catfish
    """,
     "output":"""
     {
       "classification": false,
       "reasoning": "Both the title and URL clearly indicate this article is about a fishing record, with no connection to a flood or tropical cyclone event."
     }
     """},

]

def build_title_screening_flood_prompt(url: str, title: str) -> list[dict]:
    """
    Builds a chat-style message list for use with a model's chat template.
    """
    messages = [{"role": "system", "content": ARTICLE_TITLE_SCREENING_FLOOD_PROMPT}]

    # Add few-shot examples as alternating user/assistant turns
    for example in ARTICLE_TITLE_SCREENING_FLOOD_EXAMPLES:
        messages.append({"role": "user", "content": example["input"]})
        messages.append({"role": "assistant", "content": example["output"]})

    # Add the actual query
    messages.append({"role": "user", "content": f'URL: {url}\nTITLE: {title}'})

    return messages