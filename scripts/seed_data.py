"""Seed realistic e-commerce business knowledge data.

Usage: python scripts/seed_data.py
"""

import asyncio
import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "ai_nexus.db"


def seed():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # ── Entities ──────────────────────────────────────────────────────
    # (name, type, description, domain)
    entities = [
        # 账户域
        ("用户", "actor", "平台注册用户，可以下单、支付和管理个人信息", "账户"),
        ("商户", "actor", "入驻平台的第三方商家，管理商品和发货", "账户"),
        ("管理员", "actor", "平台运营人员，负责审核和系统配置", "账户"),
        # 交易域
        ("订单", "concept", "用户提交的购买请求，包含商品列表和金额", "交易"),
        ("购物车", "concept", "用户暂存待购商品的临时容器", "交易"),
        # 支付域
        ("支付单", "concept", "用户为订单发起的支付行为", "支付"),
        ("退款单", "concept", "用户申请的退款请求，需审核后到账", "支付"),
        ("微信支付", "system", "微信支付渠道接入", "支付"),
        ("支付宝", "system", "支付宝渠道接入", "支付"),
        # 库存域
        ("商品", "object", "平台上架销售的商品，包含名称、价格等信息", "库存"),
        ("SKU", "object", "商品的具体规格单元，如颜色、尺码组合", "库存"),
        ("仓库", "object", "存储商品的物理或逻辑仓库", "库存"),
        # 物流域
        ("物流单", "object", "记录包裹从仓库到用户手中的运输过程", "物流"),
        ("配送员", "actor", "负责最后一公里配送的人员", "物流"),
        # 营销域
        ("优惠券", "concept", "用户可领取并在下单时抵扣的优惠凭证", "营销"),
        ("促销活动", "concept", "限时折扣、满减等营销活动", "营销"),
        # 客服域
        ("工单", "concept", "用户反馈问题后创建的客服处理单", "客服"),
        ("售后单", "concept", "用户申请退换货后的处理流程单", "客服"),
        # 财务域
        ("发票", "object", "用户申请开具的电子发票", "财务"),
        ("结算单", "object", "平台与商户之间的资金结算记录", "财务"),
    ]

    cur.executemany(
        "INSERT INTO entities (name, type, description, domain, status, source) "
        "VALUES (?, ?, ?, ?, 'approved', 'manual')",
        entities,
    )

    # Get all entity IDs by name for relation building
    entity_ids = {}
    for row in cur.execute("SELECT id, name FROM entities"):
        entity_ids[row[1]] = row[0]

    # ── Relations ─────────────────────────────────────────────────────
    # (source_name, relation_type, target_name, description, weight)
    relations = [
        # 订单核心链路
        ("订单", "belongs_to", "用户", "每个订单归属于一个用户", 1.0),
        ("订单", "contains", "商品", "订单中包含一个或多个商品", 1.0),
        ("订单", "triggers", "支付单", "订单提交后触发支付", 1.0),
        ("订单", "triggers", "物流单", "订单支付后触发发货", 0.9),
        ("支付单", "may_trigger", "退款单", "支付后可能触发退款", 0.3),
        ("订单", "applies", "优惠券", "下单时可使用优惠券", 0.6),
        ("订单", "generates", "发票", "订单完成后可申请发票", 0.4),
        # 用户行为链路
        ("用户", "creates", "购物车", "用户创建购物车", 1.0),
        ("用户", "submits", "工单", "用户提交客服工单", 0.5),
        ("用户", "requests", "售后单", "用户发起售后申请", 0.4),
        ("购物车", "converts_to", "订单", "购物车结算转化为订单", 1.0),
        # 商品链路
        ("商品", "has_variant", "SKU", "商品包含多个SKU规格", 1.0),
        ("商品", "stored_in", "仓库", "商品存放在仓库中", 1.0),
        ("商品", "belongs_to", "商户", "商品归属于某个商户", 1.0),
        ("SKU", "stored_in", "仓库", "SKU存放在仓库中", 0.9),
        # 支付链路
        ("支付单", "uses_channel", "微信支付", "通过微信支付完成付款", 0.5),
        ("支付单", "uses_channel", "支付宝", "通过支付宝完成付款", 0.5),
        # 物流链路
        ("物流单", "delivers_from", "仓库", "从仓库发出包裹", 1.0),
        ("物流单", "assigned_to", "配送员", "配送员负责派送", 0.9),
        # 营销链路
        ("促销活动", "provides", "优惠券", "促销活动发放优惠券", 0.8),
        ("优惠券", "applies_to", "商品", "优惠券可作用于特定商品", 0.7),
        # 商户链路
        ("商户", "generates", "结算单", "商户与平台定期结算", 1.0),
        ("商户", "manages", "商品", "商户管理自己的商品", 1.0),
        # 管理链路
        ("管理员", "reviews", "退款单", "管理员审核退款申请", 0.8),
        ("管理员", "reviews", "售后单", "管理员处理售后单", 0.8),
        ("管理员", "configures", "促销活动", "管理员创建和配置促销", 0.7),
        ("管理员", "manages", "商户", "管理员审核和管理商户", 0.6),
    ]

    cur.executemany(
        "INSERT INTO relations (source_entity_id, relation_type, target_entity_id, description, weight, status, source) "
        f"VALUES ((SELECT id FROM entities WHERE name=?), ?, (SELECT id FROM entities WHERE name=?), ?, ?, 'approved', 'manual')",
        relations,
    )

    # ── Rules ─────────────────────────────────────────────────────────
    # (name, description, domain, severity, conditions_json, status)
    rules = [
        (
            "订单状态单向流转",
            "订单状态只能按 pending → paid → shipped → completed 单向流转，"
            "禁止回退。例外：completed 状态可回退到 refunding 发起退款。",
            "交易",
            "critical",
            '{"allowed_transitions": {"pending": ["paid", "cancelled"], "paid": ["shipped", "refunding"], "shipped": ["completed"], "completed": ["refunding"], "refunding": ["refunded", "paid"]}}',
            "approved",
        ),
        (
            "禁止删除已支付订单",
            "已支付（paid）及之后状态的订单不允许物理删除，只能通过退款流程处理。",
            "交易",
            "critical",
            '{"forbidden_actions": ["delete"], "applies_to_statuses": ["paid", "shipped", "completed"]}',
            "approved",
        ),
        (
            "退款金额上限",
            "退款金额不得超过该订单的实际支付金额，含优惠券抵扣部分按比例退还。",
            "支付",
            "critical",
            '{"max_refund": "order_actual_payment", "coupon_refund_policy": "proportional"}',
            "approved",
        ),
        (
            "库存不足禁止下单",
            "当 SKU 可用库存为 0 时，前端应禁用下单按钮并提示「库存不足」。",
            "库存",
            "warning",
            '{"condition": "sku_available_stock == 0", "action": "disable_order"}',
            "approved",
        ),
        (
            "优惠券过期校验",
            "下单时需校验优惠券是否在有效期（start_time ≤ now ≤ end_time），"
            "过期优惠券自动从可用列表移除。",
            "营销",
            "warning",
            '{"validity_check": "start_time <= now <= end_time", "auto_remove_expired": true}',
            "approved",
        ),
        (
            "物流单号格式校验",
            "物流单号必须符合承运商编码规则：顺丰(SF+12位)、中通(ZTO+10位)、"
            "圆通(YTO+13位)等。",
            "物流",
            "info",
            '{"patterns": {"SF": "^SF\\\\d{12}$", "ZTO": "^ZTO\\\\d{10}$", "YTO": "^YTO\\\\d{13}$"}}',
            "approved",
        ),
        (
            "商户T+1结算周期",
            "平台与商户的资金结算采用T+1模式，即订单完成后的第二个工作日进行结算。"
            "节假日顺延。",
            "财务",
            "info",
            '{"settlement_cycle": "T+1", "holiday_policy": "postpone_to_next_workday"}',
            "approved",
        ),
        (
            "跨域关联预警",
            "当一笔订单同时触发退款和售后时，系统应自动关联工单并通知管理员。",
            "交易",
            "warning",
            '{"trigger": "refund AND after_sale", "action": "create_linked_ticket"}',
            "approved",
        ),
        (
            "支付超时自动取消",
            "订单创建后 30 分钟内未完成支付，系统自动取消订单并释放库存。",
            "支付",
            "warning",
            '{"timeout_minutes": 30, "auto_cancel": true, "release_stock": true}',
            "approved",
        ),
        (
            "商户入驻审核",
            "新商户入驻需通过资质审核（营业执照、法人信息）后方可上架商品。",
            "账户",
            "warning",
            '{"required_docs": ["business_license", "legal_person_id"], "auto_reject_missing": true}',
            "approved",
        ),
    ]

    cur.executemany(
        "INSERT INTO rules (name, description, domain, severity, conditions, status, source, confidence) "
        "VALUES (?, ?, ?, ?, ?, ?, 'manual', 1.0)",
        rules,
    )

    # Link rules to their related entities
    rule_entity_links = [
        ("订单状态单向流转", ["订单"]),
        ("禁止删除已支付订单", ["订单"]),
        ("退款金额上限", ["退款单", "支付单", "优惠券"]),
        ("库存不足禁止下单", ["SKU", "商品", "订单"]),
        ("优惠券过期校验", ["优惠券", "订单"]),
        ("物流单号格式校验", ["物流单"]),
        ("商户T+1结算周期", ["结算单", "商户", "订单"]),
        ("跨域关联预警", ["订单", "退款单", "售后单", "工单"]),
        ("支付超时自动取消", ["订单", "支付单", "SKU"]),
        ("商户入驻审核", ["商户", "管理员"]),
    ]

    for rule_name, entity_names in rule_entity_links:
        entity_id_list = [entity_ids[n] for n in entity_names if n in entity_ids]
        cur.execute(
            "UPDATE rules SET related_entity_ids = ? WHERE name = ?",
            (json.dumps(entity_id_list), rule_name),
        )

    conn.commit()
    conn.close()

    # Print summary
    conn = sqlite3.connect(DB_PATH)
    e = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
    r = conn.execute("SELECT COUNT(*) FROM relations").fetchone()[0]
    ru = conn.execute("SELECT COUNT(*) FROM rules").fetchone()[0]
    domains = conn.execute(
        "SELECT domain, COUNT(*) FROM entities GROUP BY domain ORDER BY domain"
    ).fetchall()
    conn.close()

    print(f"Seeded: {e} entities, {r} relations, {ru} rules")
    print("Domains:", ", ".join(f"{d}({c})" for d, c in domains))


if __name__ == "__main__":
    seed()
