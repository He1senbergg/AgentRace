# 标准与接口依据

本包密码原语为本次按标准写出的纯 Python 实现，未以“已审计实现”名义分发，不含第三方密码库源码，也不把标准测试或互操作验证视为安全审计。

## RFC 8017：RSAES-OAEP

https://www.rfc-editor.org/rfc/rfc8017.html

使用 §7.1.1 / §7.1.2 的 OAEP 编码解码、§B.2.1 的 MGF1；哈希固定 SHA-256，标签固定 `AgentRace/ASL1/RSA-OAEP-SHA256`。不是 Python-RSA 的 `rsa.encrypt()`（PKCS#1 v1.5），也不是裸 RSA 加密日志正文。

## RFC 8439：ChaCha20-Poly1305

https://www.rfc-editor.org/rfc/rfc8439.html

实现 §2.1 quarter round、§2.3 block、§2.4 stream cipher、§2.5 Poly1305、§2.8 AEAD。测试包含标准 §2.1.1、§2.3.2、§2.5.2、§2.8.2 的向量。遵守同一密钥内 nonce 不重复；96-bit nonce，256-bit 对称密钥，128-bit 标签。

## Python-RSA 4.9 官方源码

https://raw.githubusercontent.com/sybrenstuvel/python-rsa/version-4.9/rsa/key.py

核对 `newkeys(nbits, accurate=True, poolsize=1, exponent=65537)`、`save_pkcs1()`、`load_pkcs1()`、`PrivateKey.blinded_decrypt()`。密钥对象的公钥数字为 n/e；私钥还持有 d/p/q 等秘密值。PEM 序列化调用 pyasn1。

https://stuvel.eu/python-rsa-doc/usage.html

补充的保存/加载说明。版本接口以以上 4.9 固定标签源码为准。文档的安全注意事项也强调不要向外暴露详细解密反馈。

## 独立验证实现（只在本地测试环境使用）

https://cryptography.io/en/latest/hazmat/primitives/asymmetric/rsa/

https://cryptography.io/en/latest/hazmat/primitives/aead/

测试环境已安装 cryptography 46.0.4，用于 RSA-OAEP 与 ChaCha20Poly1305 互操作验证，以及本地备用后端。生成的参赛文件没有 cryptography 导入或依赖。

## 工程约束

平台只取回标准输出、仅上传普通单文件、平台注入端口、禁止新增平台 Python 包来自用户提供的项目约束。工具不判断比赛规则是否允许加密自定义诊断；规则与平台权限需由参赛者确认。
