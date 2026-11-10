import org.gradle.api.tasks.testing.logging.TestExceptionFormat
import org.jetbrains.kotlin.gradle.dsl.JvmTarget
import java.time.Duration

plugins {
    alias(libs.plugins.kotlin.jvm)
    alias(libs.plugins.ktlint)
}

repositories {
    mavenCentral()
}

dependencies {
    // :core brings kotlinx-serialization-json along (declared `api` there) for
    // parsing the event envelopes the harness receives over the webhook channel.
    // The suite deliberately does NOT depend on :app -- it drives ha-sip as a
    // black box, through the same stdin/webhook interface a real deployment uses.
    testImplementation(project(":core"))
    testImplementation(libs.junit.jupiter)
    testRuntimeOnly(libs.junit.platform.launcher)
    testImplementation(libs.kotest.assertions.core)
}

kotlin {
    compilerOptions {
        jvmTarget.set(JvmTarget.JVM_25)
    }
}

java {
    sourceCompatibility = JavaVersion.VERSION_25
    targetCompatibility = JavaVersion.VERSION_25
}

ktlint {
    version.set(libs.versions.ktlint.engine)
}

// The two ha-sip instances are spawned as child JVMs from the shadow jar, using
// the natively built PJSIP bindings in app/native/<arch> (produced once by
// `mise run extract-bindings`). Resolved here rather than in the test so the
// build owns all path/layout knowledge.
val nativeArch =
    when (val arch = System.getProperty("os.arch")) {
        "x86_64", "amd64" -> "amd64"
        "aarch64", "arm64" -> "aarch64"
        else -> arch
    }

tasks.test {
    useJUnitPlatform()
    dependsOn(":app:shadowJar")

    systemProperty("hasip.jar", project(":app").layout.buildDirectory.file("libs/ha-sip.jar").get().asFile.absolutePath)
    systemProperty("hasip.nativeDir", project(":app").projectDir.resolve("native/$nativeArch").absolutePath)
    if (project.hasProperty("verbose")) systemProperty("hasip.verbose", "true")
    if (project.hasProperty("sipLog")) systemProperty("hasip.sipLog", "true")

    testLogging {
        events("passed", "skipped", "failed")
        showStandardStreams = project.hasProperty("verbose")
        exceptionFormat = TestExceptionFormat.FULL
    }

    // Real SIP calls with real timeouts: minutes, not seconds. Kept serial --
    // the scenarios measure wall-clock timing and share two OS-level processes.
    timeout.set(Duration.ofMinutes(15))
    maxParallelForks = 1

    // Never up-to-date. Gradle's inputs (test classes, classpath) say nothing about
    // what this suite actually exercises: two external processes, real sockets and
    // real wall-clock timing. Being told UP-TO-DATE with no output -- and no re-run --
    // when you deliberately asked for the suite is worse than useless.
    outputs.upToDateWhen { false }

    // A run that spawns SIP stacks and takes ~40 s deserves a verdict line.
    addTestListener(
        object : TestListener {
            override fun beforeSuite(suite: TestDescriptor) = Unit

            override fun beforeTest(test: TestDescriptor) = Unit

            override fun afterTest(
                test: TestDescriptor,
                result: TestResult,
            ) = Unit

            override fun afterSuite(
                suite: TestDescriptor,
                result: TestResult,
            ) {
                // Only the synthetic root suite, which aggregates every class.
                if (suite.parent != null) return
                logger.lifecycle(
                    "\nIntegration tests: ${result.resultType} -- ${result.testCount} run, " +
                        "${result.successfulTestCount} passed, ${result.failedTestCount} failed, " +
                        "${result.skippedTestCount} skipped",
                )
            }
        },
    )

    // Opt-in: `./gradlew build` must not spawn SIP stacks and burn a minute of
    // wall clock. Run via `mise run integration-test`.
    onlyIf {
        project.hasProperty("integrationTests").also {
            if (!it) logger.lifecycle("Skipping :integration-test -- re-run with -PintegrationTests (or `mise run integration-test`).")
        }
    }
}
