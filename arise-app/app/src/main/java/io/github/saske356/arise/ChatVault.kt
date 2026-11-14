package io.github.saske356.arise

import android.content.Context
import android.os.Build
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import org.json.JSONObject
import java.io.File
import java.security.KeyStore
import java.security.SecureRandom
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.SecretKeyFactory
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.PBEKeySpec
import javax.crypto.spec.SecretKeySpec

/**
 * Хранилище чата на телефоне. Без PIN не прочитать ни переписку, ни ключи.
 *
 * Переписка зашифрована случайным ключом хранилища (AES-256-GCM). Сам ключ хранилища лежит
 * зашифрованным дважды: ключом из PIN (PBKDF2) и поверх — ключом из Android Keystore, который
 * нельзя вытащить из телефона. Поэтому перебрать PIN на компьютере, скопировав файлы, нельзя —
 * только на этом телефоне, через приложение, а оно после MAX_FAILS ошибок стирает всё.
 *
 * У каждой подписки своё хранилище, свой ключ Keystore и свой счётчик ошибок: сменили подписку
 * в приложении — чужая переписка не откроется (и наоборот).
 *
 * Два хранилища: настоящее и ложное. Ложный PIN открывает ложное — в нём своя, пустая переписка,
 * будто чатом не пользовались.
 */
object ChatVault {
    const val MAX_FAILS = 10
    private const val ALIAS = "arise_chat_wrap"
    private const val ITER = 120_000
    private val rnd = SecureRandom()

    enum class Slot(val file: String) { REAL("chat_real"), DECOY("chat_decoy") }

    private lateinit var root: File
    private lateinit var prefs: android.content.SharedPreferences

    fun init(ctx: Context) {
        root = File(ctx.filesDir, "chat").also { it.mkdirs() }
        prefs = ctx.getSharedPreferences("chat_guard", Context.MODE_PRIVATE)
        // Первая версия держала одно хранилище на всё приложение — его владелец неизвестен, убираем
        for (s in Slot.entries) {
            File(root, s.file + ".key").delete()
            File(root, s.file + ".dat").delete()
        }
        try {
            KeyStore.getInstance("AndroidKeyStore").apply { load(null) }.deleteEntry(ALIAS)
        } catch (e: Exception) {
            // ключа не было
        }
    }

    /** Отпечаток текущей подписки: по нему у каждой подписки свои файлы, ключ и счётчик. */
    fun space(): String {
        val sub = Store.subUrl.trim().substringBefore('?').trimEnd('/')
        val h = java.security.MessageDigest.getInstance("SHA-256").digest(sub.toByteArray())
        return h.take(8).joinToString("") { "%02x".format(it) }
    }

    private val dir: File get() = File(root, space()).also { it.mkdirs() }
    private val alias: String get() = ALIAS + "_" + space()
    private val failsKey: String get() = "fails_" + space()

    private fun keyFile(s: Slot) = File(dir, s.file + ".key")
    private fun dataFile(s: Slot) = File(dir, s.file + ".dat")

    fun exists(s: Slot = Slot.REAL) = keyFile(s).exists()

    // «Скрывать чат» хранится вне хранилища: главный экран решает до ввода PIN
    fun isHidden() = prefs.getBoolean("hidden_" + space(), false)
    fun setHidden(on: Boolean) = prefs.edit().putBoolean("hidden_" + space(), on).apply()
    val fails: Int get() = prefs.getInt(failsKey, 0)

    // ---------- ключи ----------

    private fun keystoreKey(): SecretKey {
        val ks = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (ks.getKey(alias, null) as? SecretKey)?.let { return it }
        val gen = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        gen.init(
            KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build()
        )
        return gen.generateKey()
    }

    private fun pinKey(pin: String, salt: ByteArray, alg: String): SecretKey {
        val spec = PBEKeySpec(pin.toCharArray(), salt, ITER, 256)
        val raw = SecretKeyFactory.getInstance(alg).generateSecret(spec).encoded
        return SecretKeySpec(raw, "AES")
    }

    private fun kdf(): String = if (Build.VERSION.SDK_INT >= 26) "PBKDF2WithHmacSHA256" else "PBKDF2WithHmacSHA1"

    private fun seal(key: SecretKey, data: ByteArray): ByteArray {
        val c = Cipher.getInstance("AES/GCM/NoPadding")
        c.init(Cipher.ENCRYPT_MODE, key)  // IV выбирает шифр (Keystore иначе не даёт)
        return c.iv + c.doFinal(data)
    }

    private fun unseal(key: SecretKey, blob: ByteArray): ByteArray {
        val c = Cipher.getInstance("AES/GCM/NoPadding")
        c.init(Cipher.DECRYPT_MODE, key, GCMParameterSpec(128, blob, 0, 12))
        return c.doFinal(blob, 12, blob.size - 12)
    }

    private fun b64(b: ByteArray) = Base64.encodeToString(b, Base64.NO_WRAP)
    private fun unb64(s: String) = Base64.decode(s, Base64.NO_WRAP)

    // ---------- открытое хранилище ----------

    class Opened internal constructor(val slot: Slot, private val key: SecretKey, var data: JSONObject) {
        /** Записать изменения (переписку, контакты, настройки) на диск зашифрованными. */
        fun save() {
            val f = ChatVault.dataFile(slot)
            val tmp = File(f.path + ".tmp")
            tmp.writeBytes(ChatVault.seal(key, data.toString().toByteArray()))
            tmp.renameTo(f)
        }

        /** Сменить PIN этого хранилища: ключ хранилища тот же, обёртка новая. */
        fun changePin(pin: String) = ChatVault.wrap(slot, key, pin)
    }

    private fun wrap(slot: Slot, vaultKey: SecretKey, pin: String) {
        val salt = ByteArray(16).also { rnd.nextBytes(it) }
        val alg = kdf()
        val inner = seal(pinKey(pin, salt, alg), vaultKey.encoded)
        val outer = seal(keystoreKey(), inner)
        val o = JSONObject().put("salt", b64(salt)).put("alg", alg).put("w", b64(outer))
        keyFile(slot).writeText(o.toString())
    }

    /** Новое хранилище под PIN (при первом входе — настоящее, в настройках — ложное). */
    fun create(slot: Slot, pin: String, data: JSONObject): Opened {
        val raw = ByteArray(32).also { rnd.nextBytes(it) }
        val key = SecretKeySpec(raw, "AES")
        wrap(slot, key, pin)
        return Opened(slot, key, data).also { it.save() }
    }

    private fun tryOpen(slot: Slot, pin: String): Opened? {
        if (!keyFile(slot).exists()) return null
        return try {
            val o = JSONObject(keyFile(slot).readText())
            val inner = unseal(keystoreKey(), unb64(o.getString("w")))
            val raw = unseal(pinKey(pin, unb64(o.getString("salt")), o.getString("alg")), inner)
            val key = SecretKeySpec(raw, "AES")
            val data = if (dataFile(slot).exists()) JSONObject(String(unseal(key, dataFile(slot).readBytes())))
            else JSONObject()
            Opened(slot, key, data)
        } catch (e: Exception) {
            null
        }
    }

    sealed class Unlock {
        class Ok(val vault: Opened) : Unlock()
        class Wrong(val left: Int) : Unlock()
        object Wiped : Unlock()
    }

    /** Ввод PIN: настоящий открывает переписку, ложный — пустую, неверный считается. */
    fun unlock(pin: String): Unlock {
        val opened = tryOpen(Slot.REAL, pin) ?: tryOpen(Slot.DECOY, pin)
        if (opened != null) {
            prefs.edit().putInt(failsKey, 0).apply()
            return Unlock.Ok(opened)
        }
        val n = fails + 1
        prefs.edit().putInt(failsKey, n).apply()
        if (n >= MAX_FAILS) {
            wipe()
            return Unlock.Wiped
        }
        return Unlock.Wrong(MAX_FAILS - n)
    }

    /** Ложный PIN не должен совпадать с настоящим: проверяем, не открывает ли он настоящее. */
    fun opensReal(pin: String) = tryOpen(Slot.REAL, pin) != null
    fun opensDecoy(pin: String) = tryOpen(Slot.DECOY, pin) != null

    /** Стереть всё (этой подписки): оба хранилища и ключ Keystore — восстановить будет невозможно. */
    fun wipe() {
        for (s in Slot.entries) {
            keyFile(s).delete()
            dataFile(s).delete()
        }
        try {
            KeyStore.getInstance("AndroidKeyStore").apply { load(null) }.deleteEntry(alias)
        } catch (e: Exception) {
            // ключа ещё не было
        }
        prefs.edit().remove(failsKey).remove("hidden_" + space()).apply()
    }

    fun dropDecoy() {
        keyFile(Slot.DECOY).delete()
        dataFile(Slot.DECOY).delete()
    }
}
