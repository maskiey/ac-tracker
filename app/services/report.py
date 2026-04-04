from __future__ import annotations


def generate_weekly_report(weekly_stats: dict, tag_stats: list[dict]) -> dict:
    ac_count = weekly_stats["ac_count"]
    attempt_count = weekly_stats["attempt_count"]
    accuracy = weekly_stats["accuracy"]

    if not attempt_count:
        return {
            "summary": "本周还没有同步到提交记录，建议先手动触发一次同步并开始刷题。",
            "highlights": ["当前数据为空，适合从建立稳定刷题节奏开始。"],
            "weaknesses": ["暂无可分析的薄弱项。"],
            "suggestion": "先设定一个每日 1 到 2 题的小目标，并完成首次数据同步。",
        }

    top_tag = tag_stats[0]["tag"] if tag_stats else "基础题"
    summary = f"本周共尝试 {attempt_count} 次，成功通过 {ac_count} 题，正确率为 {accuracy:.2f}%。"

    highlights = [f"主要刷题方向集中在 {top_tag}。"]
    if ac_count >= 10:
        highlights.append("本周通过数量较高，整体训练节奏很稳定。")
    elif ac_count >= 5:
        highlights.append("本周保持了不错的做题产出。")
    else:
        highlights.append("本周有一定练习积累，仍有继续提量空间。")

    weaknesses = []
    if accuracy < 35:
        weaknesses.append("正确率偏低，说明读题、构造或调试环节还可以再加强。")
    elif accuracy < 60:
        weaknesses.append("正确率中等，建议在总结错因后再做一轮同类题巩固。")
    else:
        weaknesses.append("正确率表现不错，可以逐步提高题目难度。")

    if len(tag_stats) <= 1:
        weaknesses.append("知识点分布偏集中，题型覆盖面还不够广。")
    elif tag_stats and tag_stats[0]["count"] >= sum(item["count"] for item in tag_stats) * 0.6:
        weaknesses.append("训练重心较为单一，建议补充其他常见算法专题。")

    if accuracy < 50:
        suggestion = f"建议下周继续做 {top_tag} 相关题目，但把重点放在复盘错题和总结模板上。"
    else:
        suggestion = f"建议在保持 {top_tag} 训练强度的同时，补充图论、贪心或搜索类题目，扩大覆盖面。"

    return {
        "summary": summary,
        "highlights": highlights,
        "weaknesses": weaknesses,
        "suggestion": suggestion,
    }
