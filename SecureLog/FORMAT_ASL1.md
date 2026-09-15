# ASL1 文件/记录格式

本格式是应用层记录封装，不是发送者签名协议或完整审计账本。

## 外层可打印行

```text
[_sl_emit_line] ASL1 <sid_hex32> <sequence> <part>/<parts> <base64_chunk>
```

同一记录的 Base64 串按最多 1400 字符分片。序号从 1 开始，范围小于 2^63。同一次加密的分片引用同一会话 ID 和序号。解析器可忽略此固定前缀之前的平台时间戳。

## Base64 解码后的二进制包

按以下顺序连接，整数为大端：

| 字段 | 长度 |
| --- | --- |
| magic = ASCII ASL1 | 4 |
| 公钥指纹 kid | 16 |
| 随机会话 ID sid | 16 |
| sequence | 8 |
| wrapped_len | 2 |
| RSA-OAEP 封装的日志密钥 | wrapped_len；3072 位为 384，4096 位为 512 |
| sealed_len | 4 |
| ChaCha20-Poly1305 密文和标签 | sealed_len |

整个表中 sealed 正文之前的包头作为 AEAD 附加认证数据 AAD。nonce = sequence.to_bytes(12, 'big')。每个会话随机生成独立 32 字节日志密钥；每条包重复携带该会话的 RSA 密文密钥包，避免头部丢失依赖。

RSA 算法：RSAES-OAEP，SHA-256、MGF1-SHA-256；label = b'AgentRace/ASL1/RSA-OAEP-SHA256'。仅允许 e=65537，模数位数 3072/4096。明文为 32 字节日志密钥。不能使用 rsa.decrypt()（旧填充）解开本包。

kid = SHA256(b'ASL1/public-key\x00' || n 的定长大端编码 || e 的4字节大端编码) 的前16字节。它是公钥标识，不是密码或发送者认证。

## AEAD 解密后的正文

`codec:1 byte || raw_len:4 bytes || stored_len:4 bytes || stored_content || zero_padding`。

codec=0 表示原字节，codec=1 表示一条独立 zlib(level=1) 数据；只有更短时才压缩。padding 为填充至 256 字节整数倍的最短全零填充。记录原文字节上限 2MiB，封装后的正文上限 256KiB。原日志文本的换行在正文内保留。

先验证标签，再解密、检查长度和填充，再有界解压。所有长度和片段上限均是本工具工程限制，不是比赛规则。

## 恢复完整性的限制

完整记录独立认证，组装顺序与 outer sid/sequence 必须匹配包头。报告缺片、缺序号、冲突与解密失败。没有受信任的终止记录或期望总条数，无法凭日志本身证明没有尾部截断、整个会话删除或重放。公钥可生成新会话，不能把认证标签当成参赛者数字签名。
