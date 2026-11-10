package io.github.arnonym.yaml

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import org.yaml.snakeyaml.Yaml

fun parseYamlToJsonElement(yamlContent: String): JsonElement {
    val loaded = Yaml().load<Any?>(yamlContent)
    return loaded.toJsonElement()
}

@Suppress("UNCHECKED_CAST")
fun Any?.toJsonElement(): JsonElement =
    when (this) {
        null -> JsonNull
        is JsonElement -> this
        is Map<*, *> -> JsonObject((this as Map<Any?, Any?>).entries.associate { (k, v) -> k.toString() to v.toJsonElement() })
        is List<*> -> JsonArray(map { it.toJsonElement() })
        is String -> JsonPrimitive(this)
        is Boolean -> JsonPrimitive(this)
        is Int -> JsonPrimitive(this)
        is Long -> JsonPrimitive(this)
        is Double -> JsonPrimitive(this)
        is Float -> JsonPrimitive(this)
        is Number -> JsonPrimitive(this.toDouble())
        else -> JsonPrimitive(this.toString())
    }
