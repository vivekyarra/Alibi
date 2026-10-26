import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
}

android {
    namespace = "dev.gridprint.capture"
    compileSdk = 35

    defaultConfig {
        applicationId = "dev.gridprint.capture"
        minSdk = 29          // MediaFormat.KEY_MAX_B_FRAMES, MediaStore.Downloads
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            // Release signing is set up by the human (BUILD.md). Debug builds are enough for H4.
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    testOptions {
        unitTests.isReturnDefaultValues = false
    }
}

kotlin {
    compilerOptions {
        jvmTarget.set(JvmTarget.JVM_17)
    }
}

dependencies {
    // No AndroidX: the app uses only the platform SDK (android.hardware.camera2, android.media).
    testImplementation(libs.junit)
}
