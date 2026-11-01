QUESTION_TYPES = {
    "code": "代码编程",
    "choice": "选择题",
    "judge": "判断题",
    "fill": "填空题",
}

SUBJECTS = {
    "信息技术": "信息技术",
    "语文": "语文",
    "数学": "数学",
    "英语": "英语",
    "科学": "科学",
    "道德与法治": "道德与法治",
    "物理": "物理",
    "化学": "化学",
    "生物": "生物",
    "历史": "历史",
    "地理": "地理",
}

STAGES = {
    "小学": "小学",
    "初中": "初中",
    "高中": "高中",
}

GRADE_LEVELS = {
    "": "全部",
    "小学一年级": "小学一年级",
    "小学二年级": "小学二年级",
    "小学三年级": "小学三年级",
    "小学四年级": "小学四年级",
    "小学五年级": "小学五年级",
    "小学六年级": "小学六年级",
    "初中一年级": "初中一年级",
    "初中二年级": "初中二年级",
    "初中三年级": "初中三年级",
    "高中一年级": "高中一年级",
    "高中二年级": "高中二年级",
    "高中三年级": "高中三年级",
}


def question_type_label(value):
    return QUESTION_TYPES.get(value, value)


def subject_label(value):
    return SUBJECTS.get(value, value)


def stage_label(value):
    return STAGES.get(value, value)


def grade_label(value):
    return GRADE_LEVELS.get(value, value)
