"""Bilingual question bank for Python basics assessment.

Contains Q1-Q10 covering: Variables, Data Types, Strings, Lists, Functions, Control Flow.
Each question includes Chinese and English versions with 4 multiple choice options.
"""

from typing import TypedDict

class Question(TypedDict):
    id: str
    topic_ids: list[str]
    difficulty: str  # easy, medium, hard
    cn: dict  # Chinese version
    en: dict  # English version

# Q1-Q10: Python Basics Bilingual Questions
BILINGUAL_QUESTIONS: list[Question] = [
    {
        "id": "q01",
        "topic_ids": ["t_variables"],
        "difficulty": "easy",
        "cn": {
            "text": "【变量】在 Python 中，以下哪个变量名是合法的？",
            "options": ["A. my_var", "B. 2my_var", "C. my-var", "D. my var"],
            "answer": "A"
        },
        "en": {
            "text": "[Variables] Which of the following is a valid variable name in Python?",
            "options": ["A. my_var", "B. 2my_var", "C. my-var", "D. my var"],
            "answer": "A"
        }
    },
    {
        "id": "q02",
        "topic_ids": ["t_data_types"],
        "difficulty": "easy",
        "cn": {
            "text": "【数据类型】Python 中，以下哪种数据类型是不可变的（immutable）？",
            "options": ["A. 列表 (list)", "B. 字典 (dictionary)", "C. 元组 (tuple)", "D. 集合 (set)"],
            "answer": "C"
        },
        "en": {
            "text": "[Data Types] Which of the following data types is immutable in Python?",
            "options": ["A. list", "B. dictionary", "C. tuple", "D. set"],
            "answer": "C"
        }
    },
    {
        "id": "q03",
        "topic_ids": ["t_strings"],
        "difficulty": "easy",
        "cn": {
            "text": "【字符串】在 Python 中，可以使用 ==、>、< 运算符来______两个字符串。",
            "options": ["A. 比较", "B. 拼接", "C. 切片", "D. 转义"],
            "answer": "A"
        },
        "en": {
            "text": "[Strings] In Python, the operators ==, >, and < can be used to ______ two strings.",
            "options": ["A. compare", "B. concatenate", "C. slice", "D. escape"],
            "answer": "A"
        }
    },
    {
        "id": "q04",
        "topic_ids": ["t_lists"],
        "difficulty": "medium",
        "cn": {
            "text": "【列表】关于 Python 列表 (list)，描述正确的是？",
            "options": [
                "A. 列表是可变序列，可以增删修改元素",
                "B. 列表一旦创建，内容不可修改",
                "C. 列表内元素必须是同一种数据类型",
                "D. 列表索引从 1 开始"
            ],
            "answer": "A"
        },
        "en": {
            "text": "[Lists] Which statement about Python lists is correct?",
            "options": [
                "A. Lists are mutable sequences; elements can be added, removed, or modified",
                "B. Once created, list contents cannot be changed",
                "C. All elements in a list must be of the same type",
                "D. List indexing starts at 1"
            ],
            "answer": "A"
        }
    },
    {
        "id": "q05",
        "topic_ids": ["t_control_flow"],
        "difficulty": "medium",
        "cn": {
            "text": "【控制流】以下代码的输出是什么？\nx = 5\nif x > 3:\n    print(\"A\")\nelif x > 4:\n    print(\"B\")\nelse:\n    print(\"C\")",
            "options": ["A. A", "B. B", "C. C", "D. 无输出"],
            "answer": "A"
        },
        "en": {
            "text": "[Control Flow] What is the output of this code?\nx = 5\nif x > 3:\n    print(\"A\")\nelif x > 4:\n    print(\"B\")\nelse:\n    print(\"C\")",
            "options": ["A. A", "B. B", "C. C", "D. No output"],
            "answer": "A"
        }
    },
    {
        "id": "q06",
        "topic_ids": ["t_functions"],
        "difficulty": "medium",
        "cn": {
            "text": "【函数】定义函数时，关键字\"def\"后面应该跟随什么？",
            "options": [
                "A. 函数名和圆括号",
                "B. 只有函数名",
                "C. 只有圆括号",
                "D. 条件表达式"
            ],
            "answer": "A"
        },
        "en": {
        "text": "[Functions] After the keyword \"def\" when defining a function, what should follow?",
            "options": [
                "A. Function name followed by parentheses",
                "B. Only the function name",
                "C. Only parentheses",
                "D. A conditional expression"
            ],
            "answer": "A"
        }
    },
    {
        "id": "q07",
        "topic_ids": ["t_dictionaries"],
        "difficulty": "medium",
        "cn": {
            "text": "【字典】如何获取字典中键\"name\"对应的值？",
            "options": [
                "A. dict[name]",
                "B. dict.get('name')",
                "C. dict['name']",
                "D. 以上都可以"
            ],
            "answer": "D"
        },
        "en": {
            "text": "[Dictionaries] How do you get the value for key 'name' in a dictionary?",
            "options": [
                "A. dict[name]",
                "B. dict.get('name')",
                "C. dict['name']",
                "D. All of the above"
            ],
            "answer": "D"
        }
    },
    {
        "id": "q08",
        "topic_ids": ["t_recursion"],
        "difficulty": "hard",
        "cn": {
            "text": "【递归】递归函数必须包含什么？",
            "options": [
                "A. 至少一个递归调用",
                "B. 基本情况（终止条件）",
                "C. 两者都需要",
                "D. 不需要特别的东西"
            ],
            "answer": "C"
        },
        "en": {
            "text": "[Recursion] What must a recursive function include?",
            "options": [
                "A. At least one recursive call",
                "B. A base case (termination condition)",
                "C. Both",
                "D. Nothing special"
            ],
            "answer": "C"
        }
    },
    {
        "id": "q09",
        "topic_ids": ["t_strings", "t_lists"],
        "difficulty": "medium",
        "cn": {
            "text": "【字符串/列表】s = \"hello\"，s[1:4] 的结果是什么？",
            "options": ["A. \"ell\"", "B. \"hel\"", "C. \"llo\"", "D. \"lo\""],
            "answer": "A"
        },
        "en": {
            "text": "[Strings/Lists] Given s = \"hello\", what is s[1:4]?",
            "options": ["A. \"ell\"", "B. \"hel\"", "C. \"llo\"", "D. \"lo\""],
            "answer": "A"
        }
    },
    {
        "id": "q10",
        "topic_ids": ["t_control_flow", "t_functions"],
        "difficulty": "hard",
        "cn": {
            "text": "【控制流/函数】以下函数的返回值是什么？\ndef test(x):\n    if x > 0:\n        return 1\n    elif x < 0:\n        return -1\n    else:\n        return 0\nresult = test(0)",
            "options": ["A. 1", "B. -1", "C. 0", "D. None"],
            "answer": "C"
        },
        "en": {
            "text": "[Control Flow/Functions] What does this function return?\ndef test(x):\n    if x > 0:\n        return 1\n    elif x < 0:\n        return -1\n    else:\n        return 0\nresult = test(0)",
            "options": ["A. 1", "B. -1", "C. 0", "D. None"],
            "answer": "C"
        }
    }
]

def get_bilingual_question(lang: str, question_id: str) -> dict | None:
    """Get a question in the specified language."""
    for q in BILINGUAL_QUESTIONS:
        if q["id"] == question_id:
            return q.get(lang) if lang in ["cn", "en"] else None
    return None

def list_bilingual_questions(lang: str, topic_ids: list[str] | None = None, difficulty: str | None = None) -> list[dict]:
    """List questions filtered by optional criteria."""
    result = []
    for q in BILINGUAL_QUESTIONS:
        # Filter by topic
        if topic_ids and not any(tid in q["topic_ids"] for tid in topic_ids):
            continue
        # Filter by difficulty
        if difficulty and q["difficulty"] != difficulty:
            continue
        # Add question in requested language
        q_data = q.get('cn') if lang == 'zh' else q.get('en') if lang == 'en' else None
        if q_data:
            result.append({
                "id": q["id"],
                "topic_ids": q["topic_ids"],
                "difficulty": q["difficulty"],
                "text": q_data["text"],
                "options": q_data["options"],
                "answer": q_data["answer"]
            })
    return result