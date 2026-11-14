package io.github.saske356.arise

import android.util.Base64
import com.google.crypto.tink.HybridDecrypt
import com.google.crypto.tink.HybridEncrypt
import com.google.crypto.tink.InsecureSecretKeyAccess
import com.google.crypto.tink.KeysetHandle
import com.google.crypto.tink.PublicKeySign
import com.google.crypto.tink.PublicKeyVerify
import com.google.crypto.tink.RegistryConfiguration
import com.google.crypto.tink.TinkProtoKeysetFormat
import com.google.crypto.tink.hybrid.HybridConfig
import com.google.crypto.tink.hybrid.PredefinedHybridParameters
import com.google.crypto.tink.signature.PredefinedSignatureParameters
import com.google.crypto.tink.signature.SignatureConfig
import org.json.JSONObject
import java.security.MessageDigest

/**
 * Шифрование чата на проверенной библиотеке Google Tink, без самописной криптографии.
 * - Сообщение шифруется открытым ключом получателя: HPKE (X25519 + HKDF-SHA256 + AES-128-GCM).
 *   Расшифровать может только телефон получателя, сервер видит шифр.
 * - Отправитель подписывает сообщение своим ключом Ed25519: сервер не может подделать письмо
 *   «от Артёма», даже если захочет.
 * - Открытый ключ устройства = {e: ключ шифрования, s: ключ подписи}; его отпечаток у двоих
 *   собеседников сравнивается как «код безопасности» — так видно, что сервер не подменил ключ.
 */
object ChatCrypto {
    private val CONTEXT = "arise-chat-v1".toByteArray()

    @Volatile
    private var ready = false

    @Synchronized
    private fun init() {
        if (ready) return
        HybridConfig.register()
        SignatureConfig.register()
        ready = true
    }

    private fun b64(b: ByteArray) = Base64.encodeToString(b, Base64.NO_WRAP)
    private fun unb64(s: String) = Base64.decode(s, Base64.NO_WRAP)

    /** Новые ключи устройства: (секретный ключ шифрования, секретный ключ подписи, открытый ключ). */
    data class Keys(val enc: String, val sign: String, val public: String)

    fun newKeys(): Keys {
        init()
        val e = KeysetHandle.generateNew(PredefinedHybridParameters.HPKE_X25519_HKDF_SHA256_AES_128_GCM)
        val s = KeysetHandle.generateNew(PredefinedSignatureParameters.ED25519)
        val pub = JSONObject()
            .put("e", b64(TinkProtoKeysetFormat.serializeKeysetWithoutSecret(e.publicKeysetHandle)))
            .put("s", b64(TinkProtoKeysetFormat.serializeKeysetWithoutSecret(s.publicKeysetHandle)))
        return Keys(
            b64(TinkProtoKeysetFormat.serializeKeyset(e, InsecureSecretKeyAccess.get())),
            b64(TinkProtoKeysetFormat.serializeKeyset(s, InsecureSecretKeyAccess.get())),
            b64(pub.toString().toByteArray())
        )
    }

    private fun publicPart(publicKey: String, part: String): KeysetHandle {
        val o = JSONObject(String(unb64(publicKey)))
        return TinkProtoKeysetFormat.parseKeysetWithoutSecret(unb64(o.getString(part)))
    }

    /**
     * Запечатать текст для получателя: подписать своим ключом и зашифровать его ключом.
     * Внутри: кто, что, когда и через сколько стереть — сервер этого не видит.
     */
    fun seal(payload: JSONObject, mySign: String, theirPublic: String): String {
        init()
        val p = payload.toString().toByteArray()
        val signer = TinkProtoKeysetFormat.parseKeyset(unb64(mySign), InsecureSecretKeyAccess.get())
            .getPrimitive(RegistryConfiguration.get(), PublicKeySign::class.java)
        val inner = JSONObject().put("p", b64(p)).put("s", b64(signer.sign(p))).toString().toByteArray()
        val enc = publicPart(theirPublic, "e").getPrimitive(RegistryConfiguration.get(), HybridEncrypt::class.java)
        return b64(enc.encrypt(inner, CONTEXT))
    }

    /** Расшифровать своим ключом. Подпись проверяется отдельно (verify), когда известен ключ отправителя. */
    fun open(box: String, myEnc: String): Pair<ByteArray, ByteArray> {
        init()
        val dec = TinkProtoKeysetFormat.parseKeyset(unb64(myEnc), InsecureSecretKeyAccess.get())
            .getPrimitive(RegistryConfiguration.get(), HybridDecrypt::class.java)
        val inner = JSONObject(String(dec.decrypt(unb64(box), CONTEXT)))
        return unb64(inner.getString("p")) to unb64(inner.getString("s"))
    }

    fun verify(payload: ByteArray, signature: ByteArray, theirPublic: String): Boolean = try {
        init()
        publicPart(theirPublic, "s").getPrimitive(RegistryConfiguration.get(), PublicKeyVerify::class.java)
            .verify(signature, payload)
        true
    } catch (e: Exception) {
        false
    }

    /** Код безопасности пары: одинаковый у обоих собеседников, 30 цифр группами по 5. */
    fun safetyNumber(a: String, b: String): String {
        val (x, y) = if (a < b) a to b else b to a
        val h = MessageDigest.getInstance("SHA-256").digest((x + "|" + y).toByteArray())
        return (0 until 6).joinToString(" ") { i ->
            val n = ((h[i * 4].toLong() and 0xff) shl 24) or ((h[i * 4 + 1].toLong() and 0xff) shl 16) or
                ((h[i * 4 + 2].toLong() and 0xff) shl 8) or (h[i * 4 + 3].toLong() and 0xff)
            "%05d".format(n % 100000)
        }
    }
}
